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
from google.cloud.sql.connector.ephemeral import _get_ephemeral
from google.cloud.sql.connector.metadata import _get_metadata
from google.cloud.sql.connector.version import __version__ as version

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
from typing import Any, Awaitable, Dict, Union

from functools import partial
import logging

logger = logging.getLogger(name=__name__)

APPLICATION_NAME = "cloud-sql-python-connector"

# The default delay is set to 55 minutes since each ephemeral certificate is only
# valid for an hour. This gives five minutes of buffer time.
_delay: int = 55 * 60



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

    :param user_agent_string:
        The user agent string to append to SQLAdmin API requests
    :type user_agent_string: str

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
                    "x-goog-api-client": self._user_agent_string,
                    "User-Agent": self._user_agent_string,
                    "Content-Type": "application/json",
                }
            )
        return self.__client_session

    _credentials: Credentials = None

    _instance_connection_string: str = None
    _user_agent_string: str = None
    _instance: str = None
    _project: str = None
    _region: str = None

    _current: asyncio.Task = None
    _next: asyncio.Task = None

    def __init__(
        self,
        instance_connection_string: str,
        driver_name: str,
        keys: concurrent.futures.Future,
        loop: asyncio.AbstractEventLoop,
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

        self._user_agent_string = f"{APPLICATION_NAME}/{version}+{driver_name}"
        self._loop = loop
        self._keys: Awaitable = asyncio.wrap_future(keys, loop=self._loop)
        self._auth_init()

        logger.debug("Updating instance data")

        self._current = self._perform_refresh()
        self._next = self._current
        asyncio.run_coroutine_threadsafe(self._current, self._loop)

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

    async def _get_instance_data(self) -> InstanceMetadata:
        """Asynchronous function that takes in the futures for the ephemeral certificate
        and the instance metadata and generates an OpenSSL context object.

        :rtype: InstanceMetadata
        :returns: A dataclass containing a string representing the ephemeral certificate, a dict
            containing the instances IP adresses, a string representing a PEM-encoded private key
            and a string representing a PEM-encoded certificate authority.
        """
        priv_key, pub_key = await self._keys

        logger.debug("Creating context")

        metadata_task = self._loop.create_task(
            _get_metadata(
                self._client_session, self._credentials, self._project, self._instance
            )
        )

        ephemeral_task = self._loop.create_task(
            _get_ephemeral(
                self._client_session,
                self._credentials,
                self._project,
                self._instance,
                pub_key,
            )
        )

        metadata, ephemeral_cert = await asyncio.gather(metadata_task, ephemeral_task)

        return InstanceMetadata(
            ephemeral_cert,
            metadata["ip_addresses"]["PRIMARY"],
            priv_key,
            metadata["server_ca_cert"],
        )

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

    async def _perform_refresh(self) -> asyncio.Task:
        """Retrieves instance metadata and ephemeral certificate from the
        Cloud SQL Instance.

        :rtype: concurrent.future.Futures
        :returns: A future representing the creation of an SSLcontext.
        """

        logger.debug("Entered _perform_refresh")

        self._current = self._loop.create_task(self._get_instance_data())
        # Ephemeral certificate expires in 1 hour, so we schedule a refresh to happen in 55 minutes.
        self._next = self._loop.create_task(self._schedule_refresh(_delay))

        return self._current

    async def _schedule_refresh(self, delay: int) -> asyncio.Task:
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

    def connect(self, driver: str, timeout: int, **kwargs):
        """A method that returns a DB-API connection to the database.

        :type driver: str
        :param driver: A string representing the driver. e.g. "pymysql"

        :type timeout: int
        :param timeout: The time limit for the connection before raising
        a TimeoutError

        :returns: A DB-API connection to the primary IP of the database.
        """

        connect_future = asyncio.run_coroutine_threadsafe(
            self._connect(driver, **kwargs), self._loop
        )

        try:
            connection = connect_future.result(timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Connection timed out after {timeout}s")
        else:
            return connection

    async def _connect(self, driver: str, **kwargs) -> Any:
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

        connect_func = {
            "pymysql": self._connect_with_pymysql,
            "pg8000": self._connect_with_pg8000,
        }

        instance_data: InstanceMetadata = await self._current

        try:
            connector = connect_func[driver]
        except KeyError:
            raise KeyError("Driver {} is not supported.".format(driver))

        connect_partial = partial(
            connector, instance_data.ip_address, instance_data.context, **kwargs
        )

        return await self._loop.run_in_executor(None, connect_partial)

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
            **kwargs,
        )
