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
from typing import Any, Dict, Optional, Type, Union

import google.auth
from google.auth.credentials import Credentials
from google.auth.credentials import with_scopes_if_required

import google.cloud.sql.connector.asyncpg as asyncpg
from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.enums import DriverMapping
from google.cloud.sql.connector.enums import IPTypes
from google.cloud.sql.connector.enums import RefreshStrategy
from google.cloud.sql.connector.exceptions import ConnectorLoopError
from google.cloud.sql.connector.exceptions import DnsNameResolutionError
from google.cloud.sql.connector.instance import RefreshAheadCache
from google.cloud.sql.connector.lazy import LazyRefreshCache
import google.cloud.sql.connector.pg8000 as pg8000
import google.cloud.sql.connector.pymysql as pymysql
import google.cloud.sql.connector.pytds as pytds
from google.cloud.sql.connector.utils import format_database_user
from google.cloud.sql.connector.utils import generate_keys

logger = logging.getLogger(name=__name__)

ASYNC_DRIVERS = ["asyncpg"]
_DEFAULT_SCHEME = "https://"
_DEFAULT_UNIVERSE_DOMAIN = "googleapis.com"
_SQLADMIN_HOST_TEMPLATE = "sqladmin.{universe_domain}"


class Connector:
    """Configure and create secure connections to Cloud SQL."""

    def __init__(
        self,
        ip_type: str | IPTypes = IPTypes.PUBLIC,
        enable_iam_auth: bool = False,
        timeout: int = 30,
        credentials: Optional[Credentials] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        quota_project: Optional[str] = None,
        sqladmin_api_endpoint: Optional[str] = None,
        user_agent: Optional[str] = None,
        universe_domain: Optional[str] = None,
        refresh_strategy: str | RefreshStrategy = RefreshStrategy.BACKGROUND,
    ) -> None:
        """Initializes a Connector instance.

        Args:
            ip_type (str | IPTypes): The default IP address type used to connect to
                Cloud SQL instances. Can be one of the following:
                IPTypes.PUBLIC ("PUBLIC"), IPTypes.PRIVATE ("PRIVATE"), or
                IPTypes.PSC ("PSC"). Default: IPTypes.PUBLIC

            enable_iam_auth (bool): Enables automatic IAM database authentication
                (Postgres and MySQL) as the default authentication method for all
                connections.

            timeout (int): The default time limit in seconds for a connection before
                raising a TimeoutError.

            credentials (google.auth.credentials.Credentials): A credentials object
                created from the google-auth Python library to be used.
                If not specified, Application Default Credentials (ADC) are used.

            quota_project (str): The Project ID for an existing Google Cloud
                project. The project specified is used for quota and billing
                purposes. If not specified, defaults to project sourced from
                environment.

            loop (asyncio.AbstractEventLoop): Event loop to run asyncio tasks, if
                not specified, defaults to creating new event loop on background
                thread.

            sqladmin_api_endpoint (str): Base URL to use when calling the Cloud SQL
                Admin API endpoint. Defaults to "https://sqladmin.googleapis.com",
                this argument should only be used in development.

            universe_domain (str): The universe domain for Cloud SQL API calls.
                Default: "googleapis.com".

            refresh_strategy (str | RefreshStrategy): The default refresh strategy
                used to refresh SSL/TLS cert and instance metadata. Can be one
                of the following: RefreshStrategy.LAZY ("LAZY") or
                RefreshStrategy.BACKGROUND ("BACKGROUND").
                Default: RefreshStrategy.BACKGROUND
        """
        # if refresh_strategy is str, convert to RefreshStrategy enum
        if isinstance(refresh_strategy, str):
            refresh_strategy = RefreshStrategy._from_str(refresh_strategy)
        self._refresh_strategy = refresh_strategy
        # if event loop is given, use for background tasks
        if loop:
            self._loop: asyncio.AbstractEventLoop = loop
            self._thread: Optional[Thread] = None
            # if lazy refresh is specified we should lazy init keys
            if self._refresh_strategy == RefreshStrategy.LAZY:
                self._keys: Optional[asyncio.Future] = None
            else:
                self._keys = loop.create_task(generate_keys())
        # if no event loop is given, spin up new loop in background thread
        else:
            self._loop = asyncio.new_event_loop()
            self._thread = Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()
            # if lazy refresh is specified we should lazy init keys
            if self._refresh_strategy == RefreshStrategy.LAZY:
                self._keys = None
            else:
                self._keys = asyncio.wrap_future(
                    asyncio.run_coroutine_threadsafe(generate_keys(), self._loop),
                    loop=self._loop,
                )
        self._cache: Dict[str, Union[RefreshAheadCache, LazyRefreshCache]] = {}
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
        self._user_agent = user_agent
        # if ip_type is str, convert to IPTypes enum
        if isinstance(ip_type, str):
            ip_type = IPTypes._from_str(ip_type)
        self._ip_type = ip_type
        self._universe_domain = universe_domain
        # construct service endpoint for Cloud SQL Admin API calls
        if not sqladmin_api_endpoint:
            self._sqladmin_api_endpoint = (
                _DEFAULT_SCHEME
                + _SQLADMIN_HOST_TEMPLATE.format(universe_domain=self.universe_domain)
            )
        # otherwise if endpoint override is passed in use it
        else:
            self._sqladmin_api_endpoint = sqladmin_api_endpoint

        # validate that the universe domain of the credentials matches the
        # universe domain of the service endpoint
        if self._credentials.universe_domain != self.universe_domain:
            raise ValueError(
                f"The configured universe domain ({self.universe_domain}) does "
                "not match the universe domain found in the credentials "
                f"({self._credentials.universe_domain}). If you haven't "
                "configured the universe domain explicitly, `googleapis.com` "
                "is the default."
            )

    @property
    def universe_domain(self) -> str:
        return self._universe_domain or _DEFAULT_UNIVERSE_DOMAIN

    def connect(
        self, instance_connection_string: str, driver: str, **kwargs: Any
    ) -> Any:
        """Connect to a Cloud SQL instance.

        Prepares and returns a database connection object connected to a Cloud
        SQL instance using SSL/TLS. Starts a background refresh to periodically
        retrieve up-to-date ephemeral certificate and instance metadata.

        Args:
            instance_connection_string (str): The instance connection name of the
                Cloud SQL instance to connect to. Takes the form of
                "project-id:region:instance-name"

                Example: "my-project:us-central1:my-instance"

            driver (str): A string representing the database driver to connect
                with. Supported drivers are pymysql, pg8000, and pytds.

            **kwargs: Any driver-specific arguments to pass to the underlying
                driver .connect call.

        Returns:
            A DB-API connection to the specified Cloud SQL instance.

        Raises:
            ConnectorLoopError: Event loop for background refresh is running in
                current thread. Error instead of hanging indefinitely.
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
        """Connect asynchronously to a Cloud SQL instance.

        Prepares and returns a database connection object connected to a Cloud
        SQL instance using SSL/TLS. Schedules a refresh to periodically
        retrieve up-to-date ephemeral certificate and instance metadata. Async
        version of Connector.connect.

        Args:
            instance_connection_string (str): The instance connection name of the
                Cloud SQL instance to connect to. Takes the form of
                "project-id:region:instance-name"

                Example: "my-project:us-central1:my-instance"

            driver (str): A string representing the database driver to connect
                with. Supported drivers are pymysql, asyncpg, pg8000, and pytds.

            **kwargs: Any driver-specific arguments to pass to the underlying
                driver .connect call.

        Returns:
            A DB-API connection to the specified Cloud SQL instance.

        Raises:
            ValueError: Connection attempt with built-in database authentication
                and then subsequent attempt with IAM database authentication.
            KeyError: Unsupported database driver Must be one of pymysql, asyncpg,
                pg8000, and pytds.
            DnsNameResolutionError: Could not resolve PSC IP address from DNS
                host name.
        """
        if self._keys is None:
            self._keys = asyncio.create_task(generate_keys())
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
        if instance_connection_string in self._cache:
            cache = self._cache[instance_connection_string]
            if enable_iam_auth != cache._enable_iam_auth:
                raise ValueError(
                    f"connect() called with 'enable_iam_auth={enable_iam_auth}', "
                    f"but previously used 'enable_iam_auth={cache._enable_iam_auth}'. "
                    "If you require both for your use case, please use a new "
                    "connector.Connector object."
                )
        else:
            if self._refresh_strategy == RefreshStrategy.LAZY:
                logger.debug(
                    f"['{instance_connection_string}']: Refresh strategy is set"
                    " to lazy refresh"
                )
                cache = LazyRefreshCache(
                    instance_connection_string,
                    self._client,
                    self._keys,
                    enable_iam_auth,
                )
            else:
                logger.debug(
                    f"['{instance_connection_string}']: Refresh strategy is set"
                    " to backgound refresh"
                )
                cache = RefreshAheadCache(
                    instance_connection_string,
                    self._client,
                    self._keys,
                    enable_iam_auth,
                )
            logger.debug(
                f"['{instance_connection_string}']: Connection info added to cache"
            )
            self._cache[instance_connection_string] = cache

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
            conn_info = await cache.connect_info()
            # validate driver matches intended database engine
            DriverMapping.validate_engine(driver, conn_info.database_version)
            ip_address = conn_info.get_preferred_ip(ip_type)
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
            logger.debug(
                f"['{instance_connection_string}']: Connecting to {ip_address}:3307"
            )
            # format `user` param for automatic IAM database authn
            if enable_iam_auth:
                formatted_user = format_database_user(
                    conn_info.database_version, kwargs["user"]
                )
                if formatted_user != kwargs["user"]:
                    logger.debug(
                        f"['{instance_connection_string}']: Truncated IAM database username from {kwargs['user']} to {formatted_user}"
                    )
                    kwargs["user"] = formatted_user

            # async drivers are unblocking and can be awaited directly
            if driver in ASYNC_DRIVERS:
                return await connector(
                    ip_address,
                    conn_info.create_ssl_context(enable_iam_auth),
                    **kwargs,
                )
            # synchronous drivers are blocking and run using executor
            connect_partial = partial(
                connector,
                ip_address,
                conn_info.create_ssl_context(enable_iam_auth),
                **kwargs,
            )
            return await self._loop.run_in_executor(None, connect_partial)

        except Exception:
            # with any exception, we attempt a force refresh, then throw the error
            await cache.force_refresh()
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
        """Helper function to cancel the cache's tasks
        and close aiohttp.ClientSession."""
        await asyncio.gather(*[cache.close() for cache in self._cache.values()])
        if self._client:
            await self._client.close()


async def create_async_connector(
    ip_type: str | IPTypes = IPTypes.PUBLIC,
    enable_iam_auth: bool = False,
    timeout: int = 30,
    credentials: Optional[Credentials] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    quota_project: Optional[str] = None,
    sqladmin_api_endpoint: Optional[str] = None,
    user_agent: Optional[str] = None,
    universe_domain: Optional[str] = None,
) -> Connector:
    """Helper function to create Connector object for asyncio connections.

    Force use of Connector in an asyncio context. Auto-detect and use current
    thread's running event loop.

    Args:
        ip_type (str | IPTypes): The default IP address type used to connect to
            Cloud SQL instances. Can be one of the following:
            IPTypes.PUBLIC ("PUBLIC"), IPTypes.PRIVATE ("PRIVATE"), or
            IPTypes.PSC ("PSC"). Default: IPTypes.PUBLIC

        enable_iam_auth (bool): Enables automatic IAM database authentication
            (Postgres and MySQL) as the default authentication method for all
            connections.

        timeout (int): The default time limit in seconds for a connection before
            raising a TimeoutError.

        credentials (google.auth.credentials.Credentials): A credentials object
            created from the google-auth Python library to be used.
            If not specified, Application Default Credentials (ADC) are used.

        quota_project (str): The Project ID for an existing Google Cloud
            project. The project specified is used for quota and billing
            purposes. If not specified, defaults to project sourced from
            environment.

        loop (asyncio.AbstractEventLoop): Event loop to run asyncio tasks, if
            not specified, defaults to creating new event loop on background
            thread.

        sqladmin_api_endpoint (str): Base URL to use when calling the Cloud SQL
            Admin API endpoint. Defaults to "https://sqladmin.googleapis.com",
            this argument should only be used in development.

    Returns:
        A Connector instance configured with running event loop.
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
