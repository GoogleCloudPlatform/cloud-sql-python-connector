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

from __future__ import annotations

import asyncio
from functools import partial
import logging
import socket
from threading import Thread
from types import TracebackType
from typing import Any, Dict, Optional, Type

import google.auth
from google.auth.credentials import Credentials
from google.auth.credentials import with_scopes_if_required

import google.cloud.sql.connector.asyncpg as asyncpg
from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.exceptions import ConnectorLoopError
from google.cloud.sql.connector.exceptions import DnsNameResolutionError
from google.cloud.sql.connector.instance import Instance
from google.cloud.sql.connector.instance import IPTypes
import google.cloud.sql.connector.pg8000 as pg8000
import google.cloud.sql.connector.pymysql as pymysql
import google.cloud.sql.connector.pytds as pytds
from google.cloud.sql.connector.utils import format_database_user
from google.cloud.sql.connector.utils import generate_keys

logger = logging.getLogger(name=__name__)

ASYNC_DRIVERS = ["asyncpg"]


class Connector:
    """A class to configure and create connections to Cloud SQL instances.

    :type ip_type: str | IPTypes
    :param ip_type
        The IP type used to connect. IP types can be either IPTypes.PUBLIC
        ("PUBLIC"), IPTypes.PRIVATE ("PRIVATE"), or IPTypes.PSC ("PSC").

    :type enable_iam_auth: bool
    :param enable_iam_auth
        Enables automatic IAM database authentication for Postgres or MySQL
        instances.

    :type timeout: int
    :param timeout
        The time limit for a connection before raising a TimeoutError.

    :type credentials: google.auth.credentials.Credentials
    :param credentials
        Credentials object used to authenticate connections to Cloud SQL server.
        If not specified, Application Default Credentials are used.

    :type quota_project: str
    :param quota_project
        The Project ID for an existing Google Cloud project. The project specified
        is used for quota and billing purposes. If not specified, defaults to
        project sourced from environment.

    :type loop: asyncio.AbstractEventLoop
    :param loop
        Event loop to run asyncio tasks, if not specified, defaults to
        creating new event loop on background thread.

    :type sqladmin_api_endpoint: str
    :param sqladmin_api_endpoint:
        Base URL to use when calling the Cloud SQL Admin API endpoint.
        Defaults to "https://sqladmin.googleapis.com", this argument should
        only be used in development.
    """

    def __init__(
        self,
        ip_type: str | IPTypes = IPTypes.PUBLIC,
        enable_iam_auth: bool = False,
        timeout: int = 30,
        credentials: Optional[Credentials] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        quota_project: Optional[str] = None,
        sqladmin_api_endpoint: str = "https://sqladmin.googleapis.com",
        user_agent: Optional[str] = None,
    ) -> None:
        # if event loop is given, use for background tasks
        if loop:
            self._loop: asyncio.AbstractEventLoop = loop
            self._thread: Optional[Thread] = None
            self._keys: asyncio.Future = loop.create_task(generate_keys())
        # if no event loop is given, spin up new loop in background thread
        else:
            self._loop = asyncio.new_event_loop()
            self._thread = Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()
            self._keys = asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(generate_keys(), self._loop),
                loop=self._loop,
            )
        self._instances: Dict[str, Instance] = {}
        self._client: Optional[CloudSQLClient] = None

        # initialize credentials
        scopes = ["https://www.googleapis.com/auth/sqlservice.admin"]
        if credentials:
            # verify custom credentials are proper type
            # and atleast base class of google.auth.credentials
            if not isinstance(credentials, Credentials):
                raise TypeError(
                    "credentials must be of type google.auth.credentials.Credentials,"
                    f" got {type(credentials)}"
                )
            self._credentials = with_scopes_if_required(credentials, scopes=scopes)
        # otherwise use application default credentials
        else:
            self._credentials, _ = google.auth.default(scopes=scopes)
        # set default params for connections
        self._timeout = timeout
        self._enable_iam_auth = enable_iam_auth
        self._quota_project = quota_project
        self._sqladmin_api_endpoint = sqladmin_api_endpoint
        self._user_agent = user_agent
        # if ip_type is str, convert to IPTypes enum
        if isinstance(ip_type, str):
            ip_type = IPTypes._from_str(ip_type)
        self._ip_type = ip_type

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
        try:
            # check if event loop is running in current thread
            if self._loop == asyncio.get_running_loop():
                raise ConnectorLoopError(
                    "Connector event loop is running in current thread!"
                    "Event loop must be attached to a different thread to prevent blocking code!"
                )
        # asyncio.get_running_loop will throw RunTimeError if no running loop is present
        except RuntimeError:
            pass

        # if event loop is not in current thread, proceed with connection
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
            pymysql, pg8000, asyncpg, and pytds.

        :param kwargs:
            Pass in any driver-specific arguments needed to connect to the Cloud
            SQL instance.

        :rtype: Connection
        :returns:
            A DB-API connection to the specified Cloud SQL instance.
        """
        # Create an Instance object from the connection string.
        # The Instance should verify arguments.
        #
        # Use the Instance to establish an SSL Connection.
        #
        # Return a DBAPI connection
        if self._client is None:
            # lazy init client as it has to be initialized in async context
            self._client = CloudSQLClient(
                self._sqladmin_api_endpoint,
                self._quota_project,
                self._credentials,
                user_agent=self._user_agent,
                driver=driver,
            )
        enable_iam_auth = kwargs.pop("enable_iam_auth", self._enable_iam_auth)
        if instance_connection_string in self._instances:
            instance = self._instances[instance_connection_string]
            if enable_iam_auth != instance._enable_iam_auth:
                raise ValueError(
                    f"connect() called with 'enable_iam_auth={enable_iam_auth}', "
                    f"but previously used 'enable_iam_auth={instance._enable_iam_auth}'. "
                    "If you require both for your use case, please use a new "
                    "connector.Connector object."
                )
        else:
            instance = Instance(
                instance_connection_string,
                self._client,
                self._keys,
                enable_iam_auth,
            )
            self._instances[instance_connection_string] = instance

        connect_func = {
            "pymysql": pymysql.connect,
            "pg8000": pg8000.connect,
            "asyncpg": asyncpg.connect,
            "pytds": pytds.connect,
        }

        # only accept supported database drivers
        try:
            connector = connect_func[driver]
        except KeyError:
            raise KeyError(f"Driver '{driver}' is not supported.")

        ip_type = kwargs.pop("ip_type", self._ip_type)
        # if ip_type is str, convert to IPTypes enum
        if isinstance(ip_type, str):
            ip_type = IPTypes._from_str(ip_type)
        kwargs["timeout"] = kwargs.get("timeout", self._timeout)

        # Host and ssl options come from the certificates and metadata, so we don't
        # want the user to specify them.
        kwargs.pop("host", None)
        kwargs.pop("ssl", None)
        kwargs.pop("port", None)

        # attempt to make connection to Cloud SQL instance
        try:
            instance_data, ip_address = await instance.connect_info(ip_type)
            # resolve DNS name into IP address for PSC
            if ip_type.value == "PSC":
                addr_info = await self._loop.getaddrinfo(
                    ip_address, None, family=socket.AF_INET, type=socket.SOCK_STREAM
                )
                # getaddrinfo returns a list of 5-tuples that contain socket
                # connection info in the form
                # (family, type, proto, canonname, sockaddr), where sockaddr is a
                # 2-tuple in the form (ip_address, port)
                try:
                    ip_address = addr_info[0][4][0]
                except IndexError as e:
                    raise DnsNameResolutionError(
                        f"['{instance_connection_string}']: DNS name could not be resolved into IP address"
                    ) from e

            # format `user` param for automatic IAM database authn
            if enable_iam_auth:
                formatted_user = format_database_user(
                    instance_data.database_version, kwargs["user"]
                )
                if formatted_user != kwargs["user"]:
                    logger.debug(
                        f"['{instance_connection_string}']: Truncated IAM database username from {kwargs['user']} to {formatted_user}"
                    )
                    kwargs["user"] = formatted_user

            # async drivers are unblocking and can be awaited directly
            if driver in ASYNC_DRIVERS:
                return await connector(ip_address, instance_data.context, **kwargs)
            # synchronous drivers are blocking and run using executor
            connect_partial = partial(
                connector, ip_address, instance_data.context, **kwargs
            )
            return await self._loop.run_in_executor(None, connect_partial)

        except Exception:
            # with any exception, we attempt a force refresh, then throw the error
            await instance.force_refresh()
            raise

    def __enter__(self) -> Any:
        """Enter context manager by returning Connector object"""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit context manager by closing Connector"""
        self.close()

    async def __aenter__(self) -> Any:
        """Enter async context manager by returning Connector object"""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit async context manager by closing Connector"""
        await self.close_async()

    def close(self) -> None:
        """Close Connector by stopping tasks and releasing resources."""
        if self._loop.is_running():
            close_future = asyncio.run_coroutine_threadsafe(
                self.close_async(), loop=self._loop
            )
            # Will attempt to safely shut down tasks for 3s
            close_future.result(timeout=3)
        # if background thread exists for Connector, clean it up
        if self._thread:
            if self._loop.is_running():
                # stop event loop running in background thread
                self._loop.call_soon_threadsafe(self._loop.stop)
            # wait for thread to finish closing (i.e. loop to stop)
            self._thread.join()

    async def close_async(self) -> None:
        """Helper function to cancel Instances' tasks
        and close aiohttp.ClientSession."""
        await asyncio.gather(
            *[instance.close() for instance in self._instances.values()]
        )
        if self._client:
            await self._client.close()


async def create_async_connector(
    ip_type: IPTypes = IPTypes.PUBLIC,
    enable_iam_auth: bool = False,
    timeout: int = 30,
    credentials: Optional[Credentials] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    quota_project: Optional[str] = None,
    sqladmin_api_endpoint: str = "https://sqladmin.googleapis.com",
    user_agent: Optional[str] = None,
) -> Connector:
    """
     Create Connector object for asyncio connections that can auto-detect
     and use current thread's running event loop.

    :type ip_type: IPTypes
     :param ip_type
         The IP type (public or private)  used to connect. IP types
         can be either IPTypes.PUBLIC or IPTypes.PRIVATE.

     :type enable_iam_auth: bool
     :param enable_iam_auth
         Enables automatic IAM database authentication for Postgres or MySQL
         instances.

     :type timeout: int
     :param timeout
         The time limit for a connection before raising a TimeoutError.

     :type credentials: google.auth.credentials.Credentials
     :param credentials
         Credentials object used to authenticate connections to Cloud SQL server.
         If not specified, Application Default Credentials are used.

     :type quota_project: str
     :param quota_project
         The Project ID for an existing Google Cloud project. The project specified
         is used for quota and billing purposes. If not specified, defaults to
         project sourced from environment.

     :type loop: asyncio.AbstractEventLoop
     :param loop
         Event loop to run asyncio tasks, if not specified, defaults to
         creating new event loop on background thread.

     :type sqladmin_api_endpoint: str
     :param sqladmin_api_endpoint:
         Base URL to use when calling the Cloud SQL Admin API endpoint.
         Defaults to "https://sqladmin.googleapis.com", this argument should
         only be used in development.
    """
    # if no loop given, automatically detect running event loop
    if loop is None:
        loop = asyncio.get_running_loop()
    return Connector(
        ip_type=ip_type,
        enable_iam_auth=enable_iam_auth,
        timeout=timeout,
        credentials=credentials,
        loop=loop,
        quota_project=quota_project,
        sqladmin_api_endpoint=sqladmin_api_endpoint,
        user_agent=user_agent,
    )
