"""
Copyright 2019 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

# Custom utils import
from google.cloud.sql.connector.utils import generate_keys

# Importing libraries
import asyncio
import aiohttp
import concurrent
import google.auth
from google.auth.credentials import Credentials
import google.auth.transport.requests
import json
import ssl
import socket
from tempfile import NamedTemporaryFile
import threading
from typing import Any, Dict, Union

import logging

logger = logging.getLogger(name=__name__)


# The default delay is set to 55 minutes since each ephemeral certificate is only
# valid for an hour. This gives five minutes of buffer time.
_delay: int = 55 * 60
_sql_api_version: str = "v1beta4"


class ConnectionSSLContext(ssl.SSLContext):
    """Subclass of ssl.SSLContext with added request_ssl attribute. This is
    required for compatibility with pg8000 driver.
    """

    def __init__(self, *args, **kwargs):
        self.request_ssl = False
        super(ConnectionSSLContext, self).__init__(*args, **kwargs)


class InstanceMetadata:
    ip_address: str
    _ca_fileobject: NamedTemporaryFile
    _cert_fileobject: NamedTemporaryFile
    _key_fileobject: NamedTemporaryFile
    context: ssl.SSLContext

    def __init__(
        self,
        ephemeral_cert: str,
        ip_address: str,
        private_key: str,
        server_ca_cert: str,
    ):
        self.ip_address = ip_address

        self._ca_fileobject = NamedTemporaryFile(suffix=".pem")
        self._cert_fileobject = NamedTemporaryFile(suffix=".pem")
        self._key_fileobject = NamedTemporaryFile(suffix=".pem")

        # Write each file and reset to beginning
        # TODO: Write tests on Windows and convert writing of temp
        # files to be compatible with Windows.
        self._ca_fileobject.write(server_ca_cert.encode())
        self._cert_fileobject.write(ephemeral_cert.encode())
        self._key_fileobject.write(private_key)

        self._ca_fileobject.seek(0)
        self._cert_fileobject.seek(0)
        self._key_fileobject.seek(0)

        self.context = ConnectionSSLContext()
        self.context.load_cert_chain(
            self._cert_fileobject.name, keyfile=self._key_fileobject.name
        )
        self.context.load_verify_locations(cafile=self._ca_fileobject.name)


class CloudSQLConnectionError(Exception):
    """
    Raised when the provided connection string is not formatted
    correctly.
    """

    def __init__(self, *args, **kwargs) -> None:
        super(CloudSQLConnectionError, self).__init__(self, *args, **kwargs)


class InstanceConnectionManager:
    """A class to manage the details of the connection, including refreshing the
    credentials.

    :param instance_connection_string:
        The Google Cloud SQL Instance's connection
        string.
    :type instance_connection_string: str
    :param loop:
        A new event loop for the refresh function to run in.
    :type loop: asyncio.AbstractEventLoop
    """

    # asyncio.AbstractEventLoop is used because the default loop,
    # SelectorEventLoop, is usable on both Unix and Windows but has limited
    # functionality on Windows. It is recommended to use ProactorEventLoop
    # while developing on Windows.
    # Link to Github issue:
    # https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/22
    _loop: asyncio.AbstractEventLoop = None

    __client_session: aiohttp.ClientSession = None

    @property
    def _client_session(self) -> aiohttp.ClientSession:
        if self.__client_session is None:
            self.__client_session = aiohttp.ClientSession(
                headers={
                    "x-goog-api-client": "cloud-sql-python-connector/0.0.1-alpha",
                    "Content-Type": "application/json",
                }
            )
        return self.__client_session

    _credentials: Credentials = None

    _instance_connection_string: str = None
    _instance: str = None
    _project: str = None
    _region: str = None

    _priv_key: str = None
    _pub_key: str = None

    _lock: threading.Lock = None
    _current: concurrent.futures.Future = None
    _next: concurrent.futures.Future = None

    def __init__(
        self, instance_connection_string: str, loop: asyncio.AbstractEventLoop
    ) -> None:
        # Validate connection string
        connection_string_split = instance_connection_string.split(":")

        if len(connection_string_split) == 3:
            self._instance_connection_string = instance_connection_string
            self._project = connection_string_split[0]
            self._region = connection_string_split[1]
            self._instance = connection_string_split[2]
        else:
            raise CloudSQLConnectionError(
                "Arg instance_connection_string must be in "
                + "format: project:region:instance."
            )

        self._loop = loop
        self._auth_init()
        self._priv_key, pub_key = generate_keys()
        self._pub_key = pub_key.decode("UTF-8")
        self._lock = threading.Lock()

        logger.debug("Updating instance data")

        with self._lock:
            self._current = self._perform_refresh()
            self._next = self.immediate_future(self._current)

    def __del__(self):
        """Deconstructor to make sure ClientSession is closed and tasks have
        finished to have a graceful exit.
        """
        logger.debug("Entering deconstructor")

        if self._current is not None:
            logger.debug("Waiting for _current_instance_data to finish")
            self._current.cancel()

        if not self._client_session.closed:
            logger.debug("Waiting for _client_session to close")
            close_future = asyncio.run_coroutine_threadsafe(
                self.__client_session.close(), loop=self._loop
            )
            close_future.result()

        logger.debug("Finished deconstructing")

    @staticmethod
    async def _get_metadata(
        client_session: aiohttp.ClientSession,
        credentials: Credentials,
        project: str,
        instance: str,
    ) -> Dict[str, Union[Dict, str]]:
        """Requests metadata from the Cloud SQL Instance
        and returns a dictionary containing the IP addresses and certificate
        authority of the Cloud SQL Instance.

        :type credentials: google.oauth2.service_account.Credentials
        :param service:
            A credentials object created from the google-auth Python library.
            Must have the SQL Admin API scopes. For more info check out
            https://google-auth.readthedocs.io/en/latest/.

        :type project: str
        :param project:
            A string representing the name of the project.

        :type inst_name: str
        :param project: A string representing the name of the instance.

        :rtype: Dict[str: Union[Dict, str]]
        :returns: Returns a dictionary containing a dictionary of all IP
              addresses and their type and a string representing the
              certificate authority.

        :raises TypeError: If any of the arguments are not the specified type.
        """

        if (
            not isinstance(credentials, Credentials)
            or not isinstance(project, str)
            or not isinstance(instance, str)
        ):
            raise TypeError(
                "Arguments must be as follows: "
                + "service (googleapiclient.discovery.Resource), "
                + "proj_name (str) and inst_name (str)."
            )

        if not credentials.valid:
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)

        headers = {
            "Authorization": "Bearer {}".format(credentials.token),
        }

        url = "https://www.googleapis.com/sql/{}/projects/{}/instances/{}".format(
            _sql_api_version, project, instance
        )

        logger.debug("Requesting metadata")

        resp = await client_session.get(url, headers=headers, raise_for_status=True)
        ret_dict = json.loads(await resp.text())

        metadata = {
            "ip_addresses": {
                ip["type"]: ip["ipAddress"] for ip in ret_dict["ipAddresses"]
            },
            "server_ca_cert": ret_dict["serverCaCert"]["cert"],
        }

        return metadata

    @staticmethod
    async def _get_ephemeral(
        client_session: aiohttp.ClientSession,
        credentials: Credentials,
        project: str,
        instance: str,
        pub_key: str,
    ) -> str:
        """Asynchronously requests an ephemeral certificate from the Cloud SQL Instance.

        :type credentials: google.oauth2.service_account.Credentials
        :param credentials: A credentials object
            created from the google-auth library. Must be
            using the SQL Admin API scopes. For more info, check out
            https://google-auth.readthedocs.io/en/latest/.

        :type project: str
        :param project : A string representing the name of the project.

        :type instance: str
        :param instance: A string representing the name of the instance.

        :type pub_key:
        :param str: A string representing PEM-encoded RSA public key.

        :rtype: str
        :returns: An ephemeral certificate from the Cloud SQL instance that allows
              authorized connections to the instance.

        :raises TypeError: If one of the arguments passed in is None.
        """

        logger.debug("Requesting ephemeral certificate")

        if (
            not isinstance(credentials, Credentials)
            or not isinstance(project, str)
            or not isinstance(instance, str)
            or not isinstance(pub_key, str)
        ):
            raise TypeError("Cannot take None as an argument.")

        if not credentials.valid:
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)

        headers = {
            "Authorization": "Bearer {}".format(credentials.token),
        }

        url = "https://www.googleapis.com/sql/{}/projects/{}/instances/{}/createEphemeral".format(
            _sql_api_version, project, instance
        )

        data = {"public_key": pub_key}

        resp = await client_session.post(
            url, headers=headers, json=data, raise_for_status=True
        )

        ret_dict = json.loads(await resp.text())

        return ret_dict["cert"]

    async def _get_instance_data(self) -> InstanceMetadata:
        """Asynchronous function that takes in the futures for the ephemeral certificate
        and the instance metadata and generates an OpenSSL context object.

        :rtype: InstanceMetadata
        :returns: A dataclass containing a string representing the ephemeral certificate, a dict
            containing the instances IP adresses, a string representing a PEM-encoded private key
            and a string representing a PEM-encoded certificate authority.
        """

        logger.debug("Creating context")

        metadata_task = self._loop.create_task(
            self._get_metadata(
                self._client_session, self._credentials, self._project, self._instance
            )
        )

        ephemeral_task = self._loop.create_task(
            self._get_ephemeral(
                self._client_session,
                self._credentials,
                self._project,
                self._instance,
                self._pub_key,
            )
        )

        metadata, ephemeral_cert = await asyncio.gather(metadata_task, ephemeral_task)

        return InstanceMetadata(
            ephemeral_cert,
            metadata["ip_addresses"]["PRIMARY"],
            self._priv_key,
            metadata["server_ca_cert"],
        )

    def _update_current(self, future: concurrent.futures.Future) -> None:
        """A threadsafe way to update the current instance data and the
        future instance data. Only meant to be called as a callback.

        :type future: asyncio.Future
        :param future: The future passed in by add_done_callback.
        """
        logger.debug("Entered _update_current")
        with self._lock:
            self._current = future
            # Ephemeral certificate expires in 1 hour, so we schedule a refresh to happen in 55 minutes.
            self._next = self._loop.create_task(self._schedule_refresh(_delay))

    def _auth_init(self) -> None:
        """Creates and assigns a Google Python API service object for
        Google Cloud SQL Admin API.
        """

        credentials, project = google.auth.default(
            scopes=[
                "https://www.googleapis.com/auth/sqlservice.admin",
                "https://www.googleapis.com/auth/cloud-platform",
            ]
        )

        self._credentials = credentials

    def _perform_refresh(self) -> concurrent.futures.Future:
        """Retrieves instance metadata and ephemeral certificate from the
        Cloud SQL Instance.

        :rtype: concurrent.future.Futures
        :returns: A future representing the creation of an SSLcontext.
        """

        logger.debug("Entered _perform_refresh")

        instance_data_task = asyncio.run_coroutine_threadsafe(
            self._get_instance_data(), loop=self._loop
        )
        instance_data_task.add_done_callback(self._update_current)

        return instance_data_task

    async def _schedule_refresh(self, delay: int) -> concurrent.futures.Future:
        """A coroutine that sleeps for the specified amount of time before
        running _perform_refresh.

        :type delay: int
        :param delay: An integer representing the number of seconds for delay.

        :rtype: asyncio.Task
        :returns: A Task representing _get_instance_data.
        """
        logger.debug("Entering sleep")

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledException:
            logger.debug("Task cancelled.")
            return None

        return self._perform_refresh()

    @staticmethod
    def immediate_future(object: Any) -> concurrent.futures.Future:
        """A static method that returns an finished future representing
        the object passed in.

        :type object: Any
        :param object: Any object.

        :rtype: concurrent.futures.Future
        :returns: A concurrent.futures.Future representing the value passed
            in.
        """
        fut: concurrent.futures.Future = concurrent.futures.Future()
        fut.set_result(object)
        return fut

    def connect(self, driver: str, **kwargs) -> Any:
        """A method that returns a DB-API connection to the database.

        :type driver: str
        :param driver: A string representing the driver. e.g. "pymysql"

        :returns: A DB-API connection to the primary IP of the database.
        """
        logger.debug("Entered connect method")

        # Host and ssl options come from the certificates and metadata, so we don't
        # want the user to specify them.
        kwargs.pop("host", None)
        kwargs.pop("ssl", None)
        kwargs.pop("port", None)

        with self._lock:
            instance_data: InstanceMetadata = self._current.result()

        connect_func = {
            "pymysql": self._connect_with_pymysql,
            "pg8000": self._connect_with_pg8000,
        }

        try:
            connector = connect_func[driver]
        except KeyError:
            raise KeyError("Driver {} is not supported.".format(driver))

        return connector(instance_data.ip_address, instance_data.context, **kwargs)

    def _connect_with_pymysql(self, ip_address: str, ctx: ssl.SSLContext, **kwargs):
        """Helper function to create a pymysql DB-API connection object.

        :type ip_address: str
        :param ip_address: A string containing an IP address for the Cloud SQL
            instance.

        :type ctx: ssl.SSLContext
        :param ctx: An SSLContext object created from the Cloud SQL server CA
            cert and ephemeral cert.

        :rtype: pymysql.Connection
        :returns: A PyMySQL Connection object for the Cloud SQL instance.
        """
        try:
            import pymysql
        except ImportError:
            raise ImportError(
                'Unable to import module "pymysql." Please install and try again.'
            )

        # Create socket and wrap with context.
        sock = ctx.wrap_socket(
            socket.create_connection((ip_address, 3307)), server_hostname=ip_address
        )

        # Create pymysql connection object and hand in pre-made connection
        conn = pymysql.Connection(host=ip_address, defer_connect=True, **kwargs)
        conn.connect(sock)
        return conn

    def _connect_with_pg8000(self, ip_address: str, ctx: ssl.SSLContext, **kwargs):
        """Helper function to create a pg8000 DB-API connection object.

        :type ip_address: str
        :param ip_address: A string containing an IP address for the Cloud SQL
            instance.

        :type ctx: ssl.SSLContext
        :param ctx: An SSLContext object created from the Cloud SQL server CA
            cert and ephemeral cert.


        :rtype: pg8000.dbapi.Connection
        :returns: A pg8000 Connection object for the Cloud SQL instance.
        """
        try:
            import pg8000
        except ImportError:
            raise ImportError(
                'Unable to import module "pg8000." Please install and try again.'
            )
        user = kwargs.pop("user")
        db = kwargs.pop("db")
        passwd = kwargs.pop("password")
        ctx.request_ssl = False
        return pg8000.dbapi.connect(
            user,
            database=db,
            password=passwd,
            host=ip_address,
            port=3307,
            ssl_context=ctx,
            **kwargs
        )
