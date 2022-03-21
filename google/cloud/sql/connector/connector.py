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
import asyncio
import concurrent
import socket
import ssl
import platform
import logging
from google.cloud.sql.connector.instance_connection_manager import (
    InstanceConnectionManager,
    IPTypes,
    PlatformNotSupportedError,
)
from google.cloud.sql.connector.utils import generate_keys
from google.auth.credentials import Credentials
from threading import Thread
from typing import Any, Dict, Optional, TYPE_CHECKING

logger = logging.getLogger(name=__name__)

_default_connector = None
SERVER_PROXY_PORT = 3307

if TYPE_CHECKING:
    import pymysql
    import pg8000
    import pytds


class Connector:
    """A class to configure and create connections to Cloud SQL instances.

    :type ip_type: IPTypes
    :param ip_type
        The IP type (public or private)  used to connect. IP types
        can be either IPTypes.PUBLIC or IPTypes.PRIVATE.

    :type enable_iam_auth: bool
    :param enable_iam_auth
        Enables IAM based authentication (Postgres only).

    :type timeout: int
    :param timeout
        The time limit for a connection before raising a TimeoutError.

    :type credentials: google.auth.credentials.Credentials
    :param credentials
        Credentials object used to authenticate connections to Cloud SQL server.
        If not specified, Application Default Credentials are used.
    """

    def __init__(
        self,
        ip_type: IPTypes = IPTypes.PUBLIC,
        enable_iam_auth: bool = False,
        timeout: int = 30,
        credentials: Optional[Credentials] = None,
    ) -> None:
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._thread: Thread = Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._keys: concurrent.futures.Future = asyncio.run_coroutine_threadsafe(
            generate_keys(), self._loop
        )
        self._instances: Dict[str, InstanceConnectionManager] = {}

        # set default params for connections
        self._timeout = timeout
        self._enable_iam_auth = enable_iam_auth
        self._ip_type = ip_type
        self._credentials = credentials

    def connect(
        self, instance_connection_string: str, driver: str, **kwargs: Any
    ) -> Any:
        """Prepares and returns a database connection object and starts a
        background task to refresh the certificates and metadata.

        :type instance_connection_string: str
        :param instance_connection_string:
            A string containing the GCP project name, region name, and instance
            name separated by colons.

            Example: example-proj:example-region-us6:example-instance

        :type driver: str
        :param: driver:
            A string representing the driver to connect with. Supported drivers are
            pymysql, pg8000, and pytds.

        :param kwargs:
            Pass in any driver-specific arguments needed to connect to the Cloud
            SQL instance.

        :rtype: Connection
        :returns:
            A DB-API connection to the specified Cloud SQL instance.
        """
        connect_task = asyncio.run_coroutine_threadsafe(
            self.connect_async(instance_connection_string, driver, **kwargs), self._loop
        )
        return connect_task.result()

    async def connect_async(
        self, instance_connection_string: str, driver: str, **kwargs: Any
    ) -> Any:
        """Prepares and returns a database connection object and starts a
        background task to refresh the certificates and metadata.

        :type instance_connection_string: str
        :param instance_connection_string:
            A string containing the GCP project name, region name, and instance
            name separated by colons.

            Example: example-proj:example-region-us6:example-instance

        :type driver: str
        :param: driver:
            A string representing the driver to connect with. Supported drivers are
            pymysql, pg8000, and pytds.

        :param kwargs:
            Pass in any driver-specific arguments needed to connect to the Cloud
            SQL instance.

        :rtype: Connection
        :returns:
            A DB-API connection to the specified Cloud SQL instance.
        """

        # Create an InstanceConnectionManager object from the connection string.
        # The InstanceConnectionManager should verify arguments.
        #
        # Use the InstanceConnectionManager to establish an SSL Connection.
        #
        # Return a DBAPI connection
        enable_iam_auth = kwargs.pop("enable_iam_auth", self._enable_iam_auth)
        if instance_connection_string in self._instances:
            icm = self._instances[instance_connection_string]
            if enable_iam_auth != icm._enable_iam_auth:
                raise ValueError(
                    f"connect() called with `enable_iam_auth={enable_iam_auth}`, "
                    f"but previously used enable_iam_auth={icm._enable_iam_auth}`. "
                    "If you require both for your use case, please use a new "
                    "connector.Connector object."
                )
        else:
            icm = InstanceConnectionManager(
                instance_connection_string,
                driver,
                self._keys,
                self._loop,
                self._credentials,
                enable_iam_auth,
            )
            self._instances[instance_connection_string] = icm

        if "ip_types" in kwargs:
            ip_type = kwargs.pop("ip_types")
            logger.warning(
                "Deprecation Warning: Parameter `ip_types` is deprecated and may be removed"
                " in a future release. Please use `ip_type` instead."
            )
        else:
            ip_type = kwargs.pop("ip_type", self._ip_type)
        timeout = kwargs.pop("timeout", self._timeout)
        if "connect_timeout" in kwargs:
            timeout = kwargs.pop("connect_timeout")

        # attempt to make connection to Cloud SQL instance for given timeout
        try:
            return await asyncio.wait_for(
                icm.connect(driver, ip_type, **kwargs), timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Connection timed out after {timeout}s")
        except Exception as e:
            # with any other exception, we attempt a force refresh, then throw the error
            icm.force_refresh()
            raise (e)

    async def _close(self) -> None:
        """Helper function to close InstanceConnectionManagers' tasks."""
        await asyncio.gather(*[icm.close() for icm in self._instances.values()])

    def __del__(self) -> None:
        """Deconstructor to make sure InstanceConnectionManagers are closed
        and tasks have finished to have a graceful exit.
        """
        logger.debug("Entering deconstructor")

        deconstruct_future = asyncio.run_coroutine_threadsafe(
            self._close(), loop=self._loop
        )
        # Will attempt to safely shut down tasks for 5s
        deconstruct_future.result(timeout=5)
        logger.debug("Finished deconstructing")


def connect(instance_connection_string: str, driver: str, **kwargs: Any) -> Any:
    """Uses a Connector object with default settings and returns a database
    connection object with a background thread to refresh the certificates and metadata.
    For more advanced configurations, callers should instantiate Connector on their own.

    :type instance_connection_string: str
    :param instance_connection_string:
        A string containing the GCP project name, region name, and instance
        name separated by colons.

        Example: example-proj:example-region-us6:example-instance

    :type driver: str
    :param: driver:
        A string representing the driver to connect with. Supported drivers are
        pymysql, pg8000, and pytds.

    :param kwargs:
        Pass in any driver-specific arguments needed to connect to the Cloud
        SQL instance.

    :rtype: Connection
    :returns:
        A DB-API connection to the specified Cloud SQL instance.
    """
    global _default_connector
    if _default_connector is None:
        _default_connector = Connector()
    return _default_connector.connect(instance_connection_string, driver, **kwargs)


def _connect_with_pymysql(
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
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
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
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
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
) -> "pytds.Connection":
    """Helper function to create a pytds DB-API connection object.

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
