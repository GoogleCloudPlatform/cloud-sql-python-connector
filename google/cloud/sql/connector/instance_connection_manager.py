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
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.cloud.sql.connector.refresh_utils import _get_ephemeral, _get_metadata
from google.cloud.sql.connector.utils import write_to_file
from google.cloud.sql.connector.version import __version__ as version

# Importing libraries
import asyncio
import aiohttp
import concurrent
import datetime
from enum import Enum
import google.auth
from google.auth.credentials import Credentials
import google.auth.transport.requests
import OpenSSL
import platform
import ssl
import socket
from tempfile import TemporaryDirectory
from typing import (
    Any,
    Awaitable,
    Dict,
    Optional,
    TYPE_CHECKING,
)

from functools import partial
import logging

if TYPE_CHECKING:
    import pymysql
    import pg8000
    import pytds
logger = logging.getLogger(name=__name__)

APPLICATION_NAME = "cloud-sql-python-connector"
SERVER_PROXY_PORT = 3307

# default_refresh_buffer is the amount of time before a refresh's result expires
# that a new refresh operation begins.
_default_refresh_buffer: int = 5 * 60  # 5 minutes

# _iam_auth_refresh_buffer is the amount of time before a refresh's result expires
# that a new refresh operation begins when IAM DB AuthN is enabled. Because token
# sources may be cached until ~60 seconds before expiration, this value must be smaller
# than default_refresh_buffer.
_iam_auth_refresh_buffer: int = 55  # seconds


class IPTypes(Enum):
    PUBLIC: str = "PRIMARY"
    PRIVATE: str = "PRIVATE"


class ConnectionSSLContext(ssl.SSLContext):
    """Subclass of ssl.SSLContext with added request_ssl attribute. This is
    required for compatibility with pg8000 driver.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.request_ssl = False
        super(ConnectionSSLContext, self).__init__(*args, **kwargs)


class TLSVersionError(Exception):
    """
    Raised when the required TLS protocol version is not supported.
    """

    def __init__(self, *args: Any) -> None:
        super(TLSVersionError, self).__init__(self, *args)


class CloudSQLConnectionError(Exception):
    """
    Raised when the provided connection string is not formatted
    correctly.
    """

    def __init__(self, *args: Any) -> None:
        super(CloudSQLConnectionError, self).__init__(self, *args)


class CloudSQLIPTypeError(Exception):
    """
    Raised when IP address for the preferred IP type is not found.
    """

    def __init__(self, *args: Any) -> None:
        super(CloudSQLIPTypeError, self).__init__(self, *args)


class PlatformNotSupportedError(Exception):
    """
    Raised when a feature is not supported on the current platform.
    """

    def __init__(self, *args: Any) -> None:
        super(PlatformNotSupportedError, self).__init__(self, *args)


class InstanceMetadata:
    ip_addrs: Dict[str, Any]
    context: ssl.SSLContext
    expiration: datetime.datetime

    def __init__(
        self,
        ephemeral_cert: str,
        ip_addrs: Dict[str, Any],
        private_key: bytes,
        server_ca_cert: str,
        expiration: datetime.datetime,
        enable_iam_auth: bool,
    ) -> None:
        self.ip_addrs = ip_addrs

        if enable_iam_auth and not ssl.HAS_TLSv1_3:  # type: ignore
            raise TLSVersionError(
                "Your current version of OpenSSL does not support TLSv1.3, "
                "which is required to use IAM Authentication."
            )

        self.context = ConnectionSSLContext()
        self.expiration = expiration

        # tmpdir and its contents are automatically deleted after the CA cert
        # and ephemeral cert are loaded into the SSLcontext. The values
        # need to be written to files in order to be loaded by the SSLContext
        with TemporaryDirectory() as tmpdir:
            ca_filename, cert_filename, key_filename = write_to_file(
                tmpdir, server_ca_cert, ephemeral_cert, private_key
            )
            self.context.load_cert_chain(cert_filename, keyfile=key_filename)
            self.context.load_verify_locations(cafile=ca_filename)

    def get_preferred_ip(self, ip_type: IPTypes) -> str:
        """Returns the first IP address for the instance, according to the preference
        supplied by ip_type. If no IP addressess with the given preference are found,
        an error is raised."""
        if ip_type.value in self.ip_addrs:
            return self.ip_addrs[ip_type.value]
        raise CloudSQLIPTypeError(
            "Cloud SQL instance does not have any IP addresses matching "
            f"preference: {ip_type.value})"
        )


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

    :param enable_iam_auth
        Enables IAM based authentication for Postgres instances.
    :type enable_iam_auth: bool

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
    _loop: asyncio.AbstractEventLoop

    _enable_iam_auth: bool

    __client_session: Optional[aiohttp.ClientSession] = None

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

    _credentials: Optional[Credentials] = None
    _keys: Awaitable

    _instance_connection_string: str
    _user_agent_string: str
    _instance: str
    _project: str
    _region: str

    _refresh_in_progress: asyncio.locks.Event
    _current: asyncio.Task  # task wraps coroutine that returns InstanceMetadata
    _next: asyncio.Task  # task wraps coroutine that returns another task

    def __init__(
        self,
        instance_connection_string: str,
        driver_name: str,
        keys: concurrent.futures.Future,
        loop: asyncio.AbstractEventLoop,
        enable_iam_auth: bool = False,
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

        self._enable_iam_auth = enable_iam_auth

        self._user_agent_string = f"{APPLICATION_NAME}/{version}+{driver_name}"
        self._loop = loop
        self._keys = asyncio.wrap_future(keys, loop=self._loop)
        self._auth_init()

        self._refresh_rate_limiter = AsyncRateLimiter(
            max_capacity=2, rate=1 / 30, loop=self._loop
        )

        async def _set_instance_data() -> None:
            logger.debug("Updating instance data")
            self._refresh_in_progress = asyncio.locks.Event(loop=self._loop)
            self._current = self._loop.create_task(self._get_instance_data())
            self._next = self._loop.create_task(self._schedule_refresh())

        init_future = asyncio.run_coroutine_threadsafe(_set_instance_data(), self._loop)
        init_future.result()

    def __del__(self) -> None:
        """Deconstructor to make sure ClientSession is closed and tasks have
        finished to have a graceful exit.
        """
        logger.debug("Entering deconstructor")

        async def _deconstruct() -> None:
            if isinstance(self._current, asyncio.Task):
                logger.debug("Waiting for _current to be cancelled")
                self._current.cancel()
            if isinstance(self._next, asyncio.Task):
                logger.debug("Waiting for _next to be cancelled")
                self._next.cancel()
            if not self._client_session.closed:
                logger.debug("Waiting for _client_session to close")
                await self._client_session.close()

        deconstruct_future = asyncio.run_coroutine_threadsafe(
            _deconstruct(), loop=self._loop
        )
        # Will attempt to safely shut down tasks for 5s
        deconstruct_future.result(timeout=5)
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
                self._enable_iam_auth,
            )
        )

        metadata, ephemeral_cert = await asyncio.gather(metadata_task, ephemeral_task)

        x509 = OpenSSL.crypto.load_certificate(
            OpenSSL.crypto.FILETYPE_PEM, ephemeral_cert
        )
        expiration = datetime.datetime.strptime(
            x509.get_notAfter().decode("ascii"), "%Y%m%d%H%M%SZ"
        )

        if self._enable_iam_auth:
            if self._credentials is not None:
                token_expiration: datetime.datetime = self._credentials.expiry
            if expiration > token_expiration:
                expiration = token_expiration

        return InstanceMetadata(
            ephemeral_cert,
            metadata["ip_addresses"],
            priv_key,
            metadata["server_ca_cert"],
            expiration,
            self._enable_iam_auth,
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

    async def _force_refresh(self) -> bool:
        if self._refresh_in_progress.is_set():
            # if a new refresh is already in progress, then block on the result
            self._current = await self._next
            return True
        try:
            self._next.cancel()
            # schedule a refresh immediately with no delay
            self._next = self._loop.create_task(self._schedule_refresh(0))
            self._current = await self._next
            return True
        except Exception as e:
            # if anything else goes wrong, log the error and return false
            logger.exception("Error occurred during force refresh attempt", exc_info=e)
            return False

    def force_refresh(self, timeout: Optional[int] = None) -> bool:
        """
        Forces a new refresh attempt and returns a boolean value that indicates
        whether the attempt was successful.

        :type timeout: Optional[int]
        :param timeout: Amount of time to wait for the attempted force refresh
        to complete before throwing a timeout error.
        """
        return asyncio.run_coroutine_threadsafe(
            self._force_refresh(), self._loop
        ).result(timeout=timeout)

    async def seconds_until_refresh(self) -> int:
        expiration = (await self._current).expiration

        if self._enable_iam_auth:
            refresh_buffer = _iam_auth_refresh_buffer
        else:
            refresh_buffer = _default_refresh_buffer

        delay = (expiration - datetime.datetime.now()) - datetime.timedelta(
            seconds=refresh_buffer
        )

        if delay.total_seconds() < 0:
            # If the time until the certificate expires is less than the buffer,
            # schedule the refresh closer to the expiration time
            delay = (expiration - datetime.datetime.now()) - datetime.timedelta(
                seconds=5
            )

        return int(delay.total_seconds())

    async def _perform_refresh(self) -> asyncio.Task:
        """Retrieves instance metadata and ephemeral certificate from the
        Cloud SQL Instance.

        :rtype: concurrent.future.Futures
        :returns: A future representing the creation of an SSLcontext.
        """
        self._refresh_in_progress.set()
        await self._refresh_rate_limiter.acquire()
        logger.debug("Entered _perform_refresh")

        refresh_task = self._loop.create_task(self._get_instance_data())

        try:
            await refresh_task
        except Exception as e:
            logger.exception(
                "An error occurred while performing refresh."
                "Scheduling another refresh attempt immediately",
                exc_info=e,
            )
            instance_data = None
            try:
                instance_data = await self._current
            except Exception:
                # Current result is invalid, no-op
                logger.debug("Current instance data is invalid.")
            if (
                instance_data is None
                or instance_data.expiration < datetime.datetime.now()
            ):
                self._current = refresh_task
                self._next = self._loop.create_task(self._perform_refresh())

        else:
            self._current = refresh_task
            # Ephemeral certificate expires in 1 hour, so we schedule a refresh to happen in 55 minutes.
            self._next = self._loop.create_task(self._schedule_refresh())
        finally:
            self._refresh_in_progress.clear()

        return refresh_task

    async def _schedule_refresh(self, delay: Optional[int] = None) -> asyncio.Task:
        """A coroutine that sleeps for the specified amount of time before
        running _perform_refresh.

        :rtype: asyncio.Task
        :returns: A Task representing _get_instance_data.
        """

        if delay is None:
            delay = await self.seconds_until_refresh()
        try:
            logger.debug("Entering sleep")
            await asyncio.sleep(delay)
        except asyncio.CancelledError as e:
            logger.debug("Schedule refresh task cancelled.")
            raise e
        return await self._perform_refresh()

    def connect(
        self,
        driver: str,
        ip_type: IPTypes,
        timeout: int,
        **kwargs: Any,
    ) -> Any:
        """A method that returns a DB-API connection to the database.

        :type driver: str
        :param driver: A string representing the driver. e.g. "pymysql"

        :type timeout: int
        :param timeout: The time limit for the connection before raising
        a TimeoutError

        :returns: A DB-API connection to the primary IP of the database.
        """

        connect_future: concurrent.futures.Future = asyncio.run_coroutine_threadsafe(
            self._connect(driver, ip_type, **kwargs), self._loop
        )

        try:
            connection = connect_future.result(timeout)
        except concurrent.futures.TimeoutError:
            connect_future.cancel()
            raise TimeoutError(f"Connection timed out after {timeout}s")
        else:
            return connection

    async def _connect(
        self,
        driver: str,
        ip_type: IPTypes,
        **kwargs: Any,
    ) -> Any:
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
            "pytds": self._connect_with_pytds,
        }

        instance_data: InstanceMetadata

        instance_data = await self._current
        ip_address: str = instance_data.get_preferred_ip(ip_type)

        try:
            connector = connect_func[driver]
        except KeyError:
            raise KeyError("Driver {} is not supported.".format(driver))

        connect_partial = partial(
            connector, ip_address, instance_data.context, **kwargs
        )

        return await self._loop.run_in_executor(None, connect_partial)

    def _connect_with_pymysql(
        self, ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
    ) -> "pymysql.connections.Connection":
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
            socket.create_connection((ip_address, SERVER_PROXY_PORT)),
            server_hostname=ip_address,
        )

        # Create pymysql connection object and hand in pre-made connection
        conn = pymysql.Connection(host=ip_address, defer_connect=True, **kwargs)
        conn.connect(sock)
        return conn

    def _connect_with_pg8000(
        self, ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
    ) -> "pg8000.dbapi.Connection":
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
        passwd = kwargs.pop("password", None)
        setattr(ctx, "request_ssl", False)
        return pg8000.dbapi.connect(
            user,
            database=db,
            password=passwd,
            host=ip_address,
            port=SERVER_PROXY_PORT,
            ssl_context=ctx,
            **kwargs,
        )

    def _connect_with_pytds(
        self, ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
    ) -> "pytds.Connection":
        """Helper function to create a pg8000 DB-API connection object.

        :type ip_address: str
        :param ip_address: A string containing an IP address for the Cloud SQL
            instance.

        :type ctx: ssl.SSLContext
        :param ctx: An SSLContext object created from the Cloud SQL server CA
            cert and ephemeral cert.


        :rtype: pytds.Connection
        :returns: A pytds Connection object for the Cloud SQL instance.
        """
        try:
            import pytds
        except ImportError:
            raise ImportError(
                'Unable to import module "pytds." Please install and try again.'
            )

        db = kwargs.pop("db", None)

        # Create socket and wrap with context.
        sock = ctx.wrap_socket(
            socket.create_connection((ip_address, SERVER_PROXY_PORT)),
            server_hostname=ip_address,
        )
        if kwargs.pop("active_directory_auth", False):
            if platform.system() == "Windows":
                # Ignore username and password if using active directory auth
                server_name = kwargs.pop("server_name")
                return pytds.connect(
                    database=db,
                    auth=pytds.login.SspiAuth(port=1433, server_name=server_name),
                    sock=sock,
                    **kwargs,
                )
            else:
                raise PlatformNotSupportedError(
                    "Active Directory authentication is currently only supported on Windows."
                )

        user = kwargs.pop("user")
        passwd = kwargs.pop("password")
        return pytds.connect(
            ip_address, database=db, user=user, password=passwd, sock=sock, **kwargs
        )
