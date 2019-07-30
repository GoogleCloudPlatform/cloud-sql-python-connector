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
import concurrent
from concurrent.futures import Future, ThreadPoolExecutor
from google.auth.credentials import Credentials
import google.auth.transport.requests
import google.auth
import logging
import OpenSSL
import requests
import socket
import threading
import time
from typing import Any, Dict, Union


logger = logging.getLogger(name=__name__)


class InstanceMetadata:
    ip_addresses: Dict[str, str]
    ssl_context: OpenSSL.SSL.Context

    def __init__(self, ssl_context, ip_addresses):
        self.ssl_context = ssl_context
        self.ip_addresses = ip_addresses


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
    _instance_connection_string: str = None
    _project: str = None
    _region: str = None
    _instance: str = None
    _priv_key: str = None
    _pub_key: str = None
    _metadata: Dict[str, Union[Dict, str]] = None

    _mutex: threading.Lock = None

    _current: Future = None
    _next: Future = None
    _executor: ThreadPoolExecutor = None

    _logger: logging.Logger = None

    def __init__(self, instance_connection_string: str) -> None:
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

        # Initialize ThreadPoolExecutor
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._auth_init()
        self._priv_key, self._pub_key = generate_keys()
        self._pub_key = self._pub_key.decode("UTF-8")
        self._mutex = threading.Lock()

        logger.debug("Updating instance data")
        self.current = self._perform_refresh()
        self._next_instance_data = self.immediate_future(self.current)

    def __del__(self):
        """Deconstructor to make sure ClientSession is closed and tasks have
        finished to have a graceful exit.
        """
        logger.debug("Entering deconstructor")

        self._next.cancel()
        self._current.cancel()
        self._executor.shutdown(wait=False)

        logger.debug("Finished deconstructing")

    @staticmethod
    def _get_metadata(
        credentials: Credentials, project: str, instance: str
    ) -> Dict[str, Union[Dict, str]]:
        """Requests metadata from the Cloud SQL Instance
        and returns a dictionary containing the IP addresses and certificate
        authority of the Cloud SQL Instance.

        :type credentials: google.auth.credentials.Credentials
        :param credentials: A google.auth.credentials.Credentials object, built using the Cloud
            SQL Admin API scopes.

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

        logger.debug("Requesting metadata")

        if not credentials.valid:
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)

        headers = {
            "Authorization": "Bearer {}".format(credentials.token),
            "Content-Type": "application/json",
        }

        url = "https://www.googleapis.com/sql/v1beta4/projects/{}/instances/{}".format(
            project, instance
        )

        response = requests.get(url, headers=headers)
        if response.status_code >= 400:
            raise ValueError("Oop")
        res = response.json()

        metadata = {
            "ip_addresses": {ip["type"]: ip["ipAddress"] for ip in res["ipAddresses"]},
            "server_ca_cert": res["serverCaCert"]["cert"],
        }

        return metadata

    @staticmethod
    def _get_ephemeral(
        credentials: Credentials, project: str, instance: str, pub_key: str
    ) -> str:
        """Requests an ephemeral certificate from the Cloud SQL Instance.

        :type credentials: google.auth.credentials.Credentials
        :param credentials: A google.auth.credentials.Credentials object, built using the Cloud
            SQL Admin API scopes.

        :type project: str
        :param project: A string representing the name of the project.

        :type instance: str
        :param instance: A string representing the name of the instance.

        :type pub_key: str
        :param pub_key: A string representing the name of the instance.

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
            "Content-Type": "application/json",
        }

        url = "https://www.googleapis.com/sql/v1beta4/projects/{}/instances/{}/createEphemeral".format(
            project, instance
        )

        data = {"public_key": pub_key}

        response = requests.post(url, headers=headers, json=data)
        res = response.json()
        cert = res["cert"]

        return cert

    def _get_instance_data(self) -> InstanceMetadata:
        """Asynchronous function that takes in the futures for the ephemeral certificate
        and the instance metadata and generates an OpenSSL context object.

        :rtype: Dict[str, Union[OpenSSL.SSL.Context, Dict]]
        :returns: A dict containing an OpenSSL context that is created using the requested ephemeral certificate
            instance metadata and a dict that contains all the instance's IP addresses.
        """

        logger.debug("Creating context")

        metadata = self._executor.submit(
            self._get_metadata, self._cloud_sql_service, self._project, self._instance
        ).result()

        ephemeral_cert = self._executor.submit(
            self._get_ephemeral,
            self._cloud_sql_service,
            self._project,
            self._instance,
            self._pub_key,
        ).result()

        return InstanceMetadata(
            self._create_context(
                self._priv_key,
                ephemeral_cert.encode(),
                metadata["server_ca_cert"].encode(),
            ),
            metadata["ip_addresses"],
        )

    def _create_context(
        self, private_key_string: str, public_cert_byte: bytes, trusted_cert_byte: bytes
    ) -> OpenSSL.SSL.Context:
        """A helper function to create an OpenSSL SSLContext object.

        :type private_key_string: str
        :param private_key_string: A string representing a PEM-encoded private key.

        :type public_cert_byte: bytes
        :param public_cert_byte: A byte string representing a PEM-encoded certificate.

        :type trusted_cert_byte: bytes
        :param trusted_cert_byte: A byte string representing a PEM-encoded certificate

        :type public_cert_byte: bytes
        :param public_cert_byte: A byte string representing a PEM-encoded certificate CA
            from the Cloud SQL Instance.

        :rtype: OpenSSL.SSL.Context
        :returns: An OpenSSL context object that contains the ephemeral certificate,
            the private key and the Cloud SQL Instance's server CA.
        """
        private_key = OpenSSL.crypto.load_privatekey(
            OpenSSL.crypto.FILETYPE_PEM, private_key_string
        )
        public_cert = OpenSSL.crypto.load_certificate(
            OpenSSL.crypto.FILETYPE_PEM, public_cert_byte
        )
        trusted_cert = OpenSSL.crypto.load_certificate(
            OpenSSL.crypto.FILETYPE_PEM, trusted_cert_byte
        )

        ctx = OpenSSL.SSL.Context(OpenSSL.SSL.TLSv1_2_METHOD)
        ctx.use_privatekey(private_key)
        ctx.use_certificate(public_cert)
        ctx.check_privatekey()
        ctx.get_cert_store().add_cert(trusted_cert)

        return ctx

    def _update_current(self, future) -> None:
        """A threadsafe way to update the current instance data and the
        future instance data. Only meant to be called as a callback.

        :type future: concurrent.futures.Future
        :param future: The future passed in by add_done_callback.
        """
        logger.debug("Entered _threadsafe_refresh")
        with self._mutex:
            self._current = future
            self._next = self._executor.submit(self._schedule_refresh, 55 * 60)

    def _auth_init(self) -> None:
        """Creates and assigns a Google Python API service object for
        Google Cloud SQL Admin API.
        """
        with threading.Lock():
            credentials, project = google.auth.default()
            scoped_credentials = credentials.with_scopes(
                [
                    "https://www.googleapis.com/auth/sqlservice.admin",
                    "https://www.googleapis.com/auth/cloud-platform",
                ]
            )

            self._credentials = scoped_credentials

    def _perform_refresh(self) -> concurrent.futures.Future:
        """Retrieves instance metadata and ephemeral certificate from the
        Cloud SQL Instance.

        :rtype: concurrent.future.Futures
        :returns: A future representing the creation of an SSLcontext.
        """

        logger.debug("Entered _perform_refresh")

        instance_data_task = self._executor.submit(self._get_instance_data)
        instance_data_task.add_done_callback(self._update_current)

        return instance_data_task

    def _schedule_refresh(self, delay: int) -> concurrent.futures.Future:
        """A corofunctionutine that sleeps for the specified amount of time before
        running _perform_refresh.

        :type delay: int
        :param delay: An integer representing the number of seconds for delay.

        :rtype: concurrent.futures.Future
        :returns: A Future representing _get_instance_data.
        """
        logger.debug("Entering sleep")

        try:
            threading.timer(delay, self._perform_refresh)
        except concurrent.futures.CancelledError:
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
        fut = concurrent.futures.Future()
        fut.set_result(object)
        return fut

    def connect(self,) -> OpenSSL.SSL.Connection:
        """A method that returns an OpenSSL connection to the database.

        :rtype: OpenSSl.SSL.Connection
        :returns: An OpenSSL connection to the primary IP of the database.
        """
        instance_data = self._current.result()
        ctx = instance_data["ssl_context"]
        ip_addr = instance_data["ip_addresses"]["PRIMARY"]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_connection = OpenSSL.SSL.Connection(ctx, s)
        ssl_connection.connect((ip_addr, 3307))
        ssl_connection.do_handshake()

        return ssl_connection
