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
import os
import socket
from threading import Thread
from types import TracebackType
from typing import Any, Callable, Optional, Union

import google.auth
from google.auth.credentials import Credentials
from google.auth.credentials import with_scopes_if_required

import google.cloud.sql.connector.asyncpg as asyncpg
from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.enums import DriverMapping
from google.cloud.sql.connector.enums import IPTypes
from google.cloud.sql.connector.enums import RefreshStrategy
from google.cloud.sql.connector.exceptions import ClosedConnectorError
from google.cloud.sql.connector.exceptions import ConnectorLoopError
from google.cloud.sql.connector.instance import RefreshAheadCache
from google.cloud.sql.connector.lazy import LazyRefreshCache
from google.cloud.sql.connector.monitored_cache import MonitoredCache
import google.cloud.sql.connector.pg8000 as pg8000
import google.cloud.sql.connector.pymysql as pymysql
import google.cloud.sql.connector.pytds as pytds
from google.cloud.sql.connector.resolver import DefaultResolver
from google.cloud.sql.connector.resolver import DnsResolver
from google.cloud.sql.connector.utils import format_database_user
from google.cloud.sql.connector.utils import generate_keys

logger = logging.getLogger(name=__name__)

ASYNC_DRIVERS = ["asyncpg"]
SERVER_PROXY_PORT = 3307
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
        resolver: type[DefaultResolver] | type[DnsResolver] = DefaultResolver,
        failover_period: int = 30,
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

            resolver (DefaultResolver | DnsResolver): The class name of the
                resolver to use for resolving the Cloud SQL instance connection
                name. To resolve a DNS record to an instance connection name, use
                DnsResolver.
                Default: DefaultResolver

            failover_period (int): The time interval in seconds between each
                attempt to check if a failover has occured for a given instance.
                Must be used with `resolver=DnsResolver` to have any effect.
                Default: 30
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
        # initialize dict to store caches, key is a tuple consisting of instance
        # connection name string and enable_iam_auth boolean flag
        self._cache: dict[tuple[str, bool], MonitoredCache] = {}
        self._client: Optional[CloudSQLClient] = None
        self._closed: bool = False

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
        self._user_agent = user_agent
        self._resolver = resolver()
        self._failover_period = failover_period
        # if ip_type is str, convert to IPTypes enum
        if isinstance(ip_type, str):
            ip_type = IPTypes._from_str(ip_type)
        self._ip_type = ip_type
        # check for quota project arg and then env var
        if quota_project:
            self._quota_project = quota_project
        else:
            self._quota_project = os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT")  # type: ignore
        # check for universe domain arg and then env var
        if universe_domain:
            self._universe_domain = universe_domain
        else:
            self._universe_domain = os.environ.get("GOOGLE_CLOUD_UNIVERSE_DOMAIN")  # type: ignore
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
        """

        # connect runs sync database connections on background thread.
        # Async database connections should call 'connect_async' directly to
        # avoid hanging indefinitely.

        # Check if the connector is closed before attempting to connect.
        if self._closed:
            raise ClosedConnectorError(
                "Connection attempt failed because the connector has already been closed."
            )
        connect_future = asyncio.run_coroutine_threadsafe(
            self.connect_async(instance_connection_string, driver, **kwargs),
            self._loop,
        )
        return connect_future.result()

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
            RuntimeError: Connector has been closed. Cannot connect using a closed
                Connector.
        """
        if self._closed:
            raise ClosedConnectorError(
                "Connection attempt failed because the connector has already been closed."
            )
        # check if event loop is running in current thread
        if self._loop != asyncio.get_running_loop():
            raise ConnectorLoopError(
                "Running event loop does not match 'connector._loop'. "
                "Connector.connect_async() must be called from the event loop "
                "the Connector was initialized with. If you need to connect "
                "across event loops, please use a new Connector object."
            )

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

        conn_name = await self._resolver.resolve(instance_connection_string)
        # Cache entry must exist and not be closed
        if (str(conn_name), enable_iam_auth) in self._cache and not self._cache[
            (str(conn_name), enable_iam_auth)
        ].closed:
            monitored_cache = self._cache[(str(conn_name), enable_iam_auth)]
        else:
            if self._refresh_strategy == RefreshStrategy.LAZY:
                logger.debug(
                    f"['{conn_name}']: Refresh strategy is set to lazy refresh"
                )
                cache: Union[LazyRefreshCache, RefreshAheadCache] = LazyRefreshCache(
                    conn_name,
                    self._client,
                    self._keys,
                    enable_iam_auth,
                )
            else:
                logger.debug(
                    f"['{conn_name}']: Refresh strategy is set to backgound refresh"
                )
                cache = RefreshAheadCache(
                    conn_name,
                    self._client,
                    self._keys,
                    enable_iam_auth,
                )
            # wrap cache as a MonitoredCache
            monitored_cache = MonitoredCache(
                cache,
                self._failover_period,
                self._resolver,
            )
            logger.debug(f"['{conn_name}']: Connection info added to cache")
            self._cache[(str(conn_name), enable_iam_auth)] = monitored_cache

        connect_func = {
            "pymysql": pymysql.connect,
            "pg8000": pg8000.connect,
            "asyncpg": asyncpg.connect,
            "pytds": pytds.connect,
        }

        # only accept supported database drivers
        try:
            connector: Callable = connect_func[driver]  # type: ignore
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

        # attempt to get connection info for Cloud SQL instance
        try:
            conn_info = await monitored_cache.connect_info()
            # validate driver matches intended database engine
            DriverMapping.validate_engine(driver, conn_info.database_version)
            ip_address = conn_info.get_preferred_ip(ip_type)
        except Exception:
            # with an error from Cloud SQL Admin API call or IP type, invalidate
            # the cache and re-raise the error
            await self._remove_cached(str(conn_name), enable_iam_auth)
            raise

        # If the connector is configured with a custom DNS name, attempt to use
        # that DNS name to connect to the instance. Fall back to the metadata IP
        # address if the DNS name does not resolve to an IP address.
        if conn_info.conn_name.domain_name and isinstance(self._resolver, DnsResolver):
            try:
                ips = await self._resolver.resolve_a_record(conn_info.conn_name.domain_name)
                if ips:
                    ip_address = ips[0]
                    logger.debug(
                        f"['{instance_connection_string}']: Custom DNS name "
                        f"'{conn_info.conn_name.domain_name}' resolved to '{ip_address}', "
                        "using it to connect"
                    )
                else:
                    logger.debug(
                        f"['{instance_connection_string}']: Custom DNS name "
                        f"'{conn_info.conn_name.domain_name}' resolved but returned no "
                        f"entries, using '{ip_address}' from instance metadata"
                    )
            except Exception as e:
                logger.debug(
                    f"['{instance_connection_string}']: Custom DNS name "
                    f"'{conn_info.conn_name.domain_name}' did not resolve to an IP "
                    f"address: {e}, using '{ip_address}' from instance metadata"
                )

        logger.debug(f"['{conn_info.conn_name}']: Connecting to {ip_address}:3307")
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
        try:
            # async drivers are unblocking and can be awaited directly
            if driver in ASYNC_DRIVERS:
                return await connector(
                    ip_address,
                    await conn_info.create_ssl_context(enable_iam_auth),
                    **kwargs,
                )
            # Create socket with SSLContext for sync drivers
            ctx = await conn_info.create_ssl_context(enable_iam_auth)
            sock = ctx.wrap_socket(
                socket.create_connection((ip_address, SERVER_PROXY_PORT)),
                server_hostname=ip_address,
            )
            # If this connection was opened using a domain name, then store it
            # for later in case we need to forcibly close it on failover.
            if conn_info.conn_name.domain_name:
                monitored_cache.sockets.append(sock)
            # Synchronous drivers are blocking and run using executor
            connect_partial = partial(
                connector,
                ip_address,
                sock,
                **kwargs,
            )
            return await self._loop.run_in_executor(None, connect_partial)

        except Exception:
            # with any exception, we attempt a force refresh, then throw the error
            await monitored_cache.force_refresh()
            raise

    async def _remove_cached(
        self, instance_connection_string: str, enable_iam_auth: bool
    ) -> None:
        """Stops all background refreshes and deletes the connection
        info cache from the map of caches.
        """
        logger.debug(
            f"['{instance_connection_string}']: Removing connection info from cache"
        )
        # remove cache from stored caches and close it
        cache = self._cache.pop((instance_connection_string, enable_iam_auth))
        await cache.close()

    def __enter__(self) -> Any:
        """Enter context manager by returning Connector object"""
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
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
        exc_type: Optional[type[BaseException]],
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
        self._closed = True
        if self._client:
            await self._client.close()
        await asyncio.gather(*[cache.close() for cache in self._cache.values()])


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
    refresh_strategy: str | RefreshStrategy = RefreshStrategy.BACKGROUND,
    resolver: type[DefaultResolver] | type[DnsResolver] = DefaultResolver,
    failover_period: int = 30,
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

        universe_domain (str): The universe domain for Cloud SQL API calls.
                Default: "googleapis.com".

        refresh_strategy (str | RefreshStrategy): The default refresh strategy
            used to refresh SSL/TLS cert and instance metadata. Can be one
            of the following: RefreshStrategy.LAZY ("LAZY") or
            RefreshStrategy.BACKGROUND ("BACKGROUND").
            Default: RefreshStrategy.BACKGROUND

        resolver (DefaultResolver | DnsResolver): The class name of the
            resolver to use for resolving the Cloud SQL instance connection
            name. To resolve a DNS record to an instance connection name, use
            DnsResolver.
            Default: DefaultResolver

        failover_period (int): The time interval in seconds between each
            attempt to check if a failover has occured for a given instance.
            Must be used with `resolver=DnsResolver` to have any effect.
            Default: 30

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
        universe_domain=universe_domain,
        refresh_strategy=refresh_strategy,
        resolver=resolver,
        failover_period=failover_period,
    )
