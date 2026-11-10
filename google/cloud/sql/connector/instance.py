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
from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from datetime import UTC
import logging

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.connection_info import ConnectionInfoCache
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.enums import IPTypes
from google.cloud.sql.connector.exceptions import RefreshNotValidError
from google.cloud.sql.connector.postgres_connection import build_postgres_startup_packet
from google.cloud.sql.connector.postgres_connection import build_terminate_packet
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.cloud.sql.connector.refresh_utils import _is_valid
from google.cloud.sql.connector.refresh_utils import _seconds_until_refresh

logger = logging.getLogger(name=__name__)

APPLICATION_NAME = "cloud-sql-python-connector"
SERVER_PROXY_PORT = 3307
DEFAULT_CONNECT_TIMEOUT = 30


class RefreshAheadCache(ConnectionInfoCache):
    """Cache that refreshes connection info in the background prior to expiration.

    Background tasks are used to schedule refresh attempts to get a new
    ephemeral certificate and Cloud SQL metadata (IP addresses, etc.) ahead of
    expiration.
    """

    def __init__(
        self,
        conn_name: ConnectionName,
        client: CloudSQLClient,
        keys: asyncio.Future,
        enable_iam_auth: bool = False,
        ip_type: IPTypes | str = IPTypes.PUBLIC,
        timeout: int = DEFAULT_CONNECT_TIMEOUT,
        dial_func: (
            Callable[
                [ConnectionInfo],
                Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]],
            ]
            | None
        ) = None,
    ) -> None:
        """Initializes a RefreshAheadCache instance.

        Args:
            conn_name (ConnectionName): The Cloud SQL instance's
                connection name.
            client (CloudSQLClient): The Cloud SQL Client instance.
            keys (asyncio.Future): A future to the client's public-private key
                pair.
            enable_iam_auth (bool): Enables automatic IAM database authentication
                (Postgres and MySQL) as the default authentication method for all
                connections.
            ip_type (IPTypes | str): Preferred IP type used to connect to the instance.
            timeout (int): Connect timeout in seconds.
            dial_func: Optional callable to dial probe connections.
        """
        self._conn_name = conn_name

        self._enable_iam_auth = enable_iam_auth
        if isinstance(ip_type, str):
            ip_type = IPTypes._from_str(ip_type)
        self._ip_type = ip_type
        self._timeout = timeout
        self._dial_func = dial_func
        self._keys = keys
        self._client = client
        self._refresh_rate_limiter = AsyncRateLimiter(
            max_capacity=2,
            rate=1 / 30,
        )
        self._refresh_in_progress = asyncio.locks.Event()
        self._iam_principals: list[tuple[str, str]] = []
        self._current: asyncio.Task = self._schedule_refresh(0)
        self._next: asyncio.Task = self._current
        self._closed = False

    def record_principal(self, user: str, database: str) -> None:
        """Records a PostgreSQL (user, database) pair observed on an IAM connection."""
        _append_iam_principal(self._iam_principals, user, database)

    @property
    def conn_name(self) -> ConnectionName:
        return self._conn_name

    @property
    def closed(self) -> bool:
        return self._closed

    async def force_refresh(self) -> None:
        """
        Forces a new refresh attempt immediately to be used for future connection attempts.
        """
        # if next refresh is not already in progress, cancel it and schedule new one immediately
        if not self._refresh_in_progress.is_set():
            self._next.cancel()
            self._next = self._schedule_refresh(0)
        # block all sequential connection attempts on the next refresh result if current is invalid
        if not await _is_valid(self._current):
            self._current = self._next

    async def _perform_refresh(self) -> ConnectionInfo:
        """Retrieves instance metadata and ephemeral certificate from the
        Cloud SQL Instance.

        Returns:
            A ConnectionInfo instance containing a string representing the
            ephemeral certificate, a dict containing the instances IP adresses,
            a string representing a PEM-encoded private key and a string
            representing a PEM-encoded certificate authority.
        """
        self._refresh_in_progress.set()
        logger.debug(
            f"['{self._conn_name}']: Connection info refresh operation started"
        )

        try:
            await self._refresh_rate_limiter.acquire()
            connection_info = await self._client.get_connection_info(
                self._conn_name,
                self._keys,
                self._enable_iam_auth,
            )
            if self._enable_iam_auth:
                await self._probe_connection(connection_info)
            logger.debug(
                f"['{self._conn_name}']: Connection info refresh operation complete"
            )
            logger.debug(
                f"['{self._conn_name}']: Current certificate "
                f"expiration = {connection_info.expiration.isoformat()}"
            )

        except Exception as e:
            logger.debug(
                f"['{self._conn_name}']: Connection info "
                f"refresh operation failed: {e!s}"
            )
            raise

        finally:
            self._refresh_in_progress.clear()
        return connection_info

    async def _probe_connection(self, conn_info: ConnectionInfo) -> None:
        """Proactively probes the database to refresh IAM tokens on server-side MCP."""
        await _probe_instance_connection(
            self._conn_name,
            conn_info,
            self._enable_iam_auth,
            self._ip_type,
            self._timeout,
            self._iam_principals,
            self._dial_func,
        )

    def _schedule_refresh(self, delay: int) -> asyncio.Task:
        """
        Schedule task to sleep and then perform refresh to get ConnectionInfo.

        Args:
            delay (int): Time in seconds to sleep before performing a refresh.

        Returns:
            An asyncio.Task representing the scheduled refresh.
        """

        async def _refresh_task(self: RefreshAheadCache, delay: int) -> ConnectionInfo:
            """
            A coroutine that sleeps for the specified amount of time before
            running _perform_refresh.
            """
            refresh_task: asyncio.Task
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                refresh_task = asyncio.create_task(self._perform_refresh())
                refresh_data = await refresh_task
                # check that refresh is valid
                if not await _is_valid(refresh_task):
                    raise RefreshNotValidError(
                        f"['{self._conn_name}']: Invalid refresh operation. Certficate appears to be expired."
                    )
            except asyncio.CancelledError:
                logger.debug(
                    f"['{self._conn_name}']: Scheduled refresh" " operation cancelled"
                )
                raise
            # bad refresh attempt
            except Exception as e:
                logger.exception(
                    f"['{self._conn_name}']: "
                    "An error occurred while performing refresh. "
                    "Scheduling another refresh attempt immediately",
                    exc_info=e,
                )
                # check if current metadata is invalid (expired),
                # don't want to replace valid metadata with invalid refresh
                if not await _is_valid(self._current):
                    self._current = refresh_task
                # schedule new refresh attempt immediately
                self._next = self._schedule_refresh(0)
                raise
            # if valid refresh, replace current with valid metadata and schedule next refresh
            self._current = refresh_task
            # calculate refresh delay based on certificate expiration
            delay = _seconds_until_refresh(refresh_data.expiration)
            logger.debug(
                f"['{self._conn_name}']: Connection info refresh"
                " operation scheduled for "
                f"{(datetime.now(UTC) + timedelta(seconds=delay)).isoformat(timespec='seconds')} "
                f"(now + {timedelta(seconds=delay)})"
            )
            self._next = self._schedule_refresh(delay)

            return refresh_data

        # schedule refresh task and return it
        scheduled_task = asyncio.create_task(_refresh_task(self, delay))
        return scheduled_task

    async def connect_info(self) -> ConnectionInfo:
        """Retrieves ConnectionInfo instance for establishing a secure
        connection to the Cloud SQL instance.
        """
        return await self._current

    async def close(self) -> None:
        """Cleanup function to make sure tasks have finished to have a
        graceful exit.
        """
        logger.debug(
            f"['{self._conn_name}']: Canceling connection info "
            "refresh operation tasks"
        )
        self._current.cancel()
        self._next.cancel()
        # gracefully wait for tasks to cancel
        tasks = asyncio.gather(self._current, self._next, return_exceptions=True)
        await asyncio.wait_for(tasks, timeout=2.0)
        self._closed = True


def _append_iam_principal(
    principals: list[tuple[str, str]], user: str, database: str
) -> None:
    """Appends (user, database) to principals if not already present."""
    if not user:
        return
    if not database:
        database = user
    pair = (user, database)
    if pair not in principals:
        principals.append(pair)


async def _probe_instance_connection(
    conn_name: ConnectionName,
    conn_info: ConnectionInfo,
    enable_iam_auth: bool,
    ip_type: IPTypes,
    timeout: int,
    iam_principals: list[tuple[str, str]],
    dial_func: (
        Callable[
            [ConnectionInfo],
            Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]],
        ]
        | None
    ) = None,
) -> None:
    """Proactively probes the database to refresh IAM tokens on server-side MCP."""
    if not enable_iam_auth:
        return

    # Proactive IAM refresh probe is PostgreSQL-only.
    if not conn_info.database_version.startswith("POSTGRES"):
        logger.debug(
            f"['{conn_name}']: Proactive IAM token refresh probe skipped: instance engine '{conn_info.database_version}' is not PostgreSQL"
        )
        return

    # Do not probe if no IAM principals have connected yet.
    if not iam_principals:
        logger.debug(
            f"['{conn_name}']: Proactive IAM token refresh probe skipped: no IAM principals connected"
        )
        return

    targets: list[str] = []
    ssl_context = None
    if dial_func is None:
        if conn_name.domain_name:
            targets.append(conn_name.domain_name)
        if ip_type.value in conn_info.ip_addrs:
            targets.extend(conn_info.ip_addrs[ip_type.value])

        if not targets:
            logger.debug(
                f"['{conn_name}']: Proactive IAM token refresh probe skipped: no target IP addresses"
            )
            return

        try:
            ssl_context = await conn_info.create_ssl_context(enable_iam_auth)
        except Exception as e:  # noqa: BLE001
            logger.debug(
                f"['{conn_name}']: Failed to create SSL context for probe: {e!s}"
            )
            return

    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(max(1, timeout))

    all_succeeded = True
    for user, database in list(iam_principals):
        remaining = deadline - loop.time()
        if remaining <= 0:
            all_succeeded = False
            break

        probed_principal = False
        if dial_func is not None:
            try:
                reader, writer = await asyncio.wait_for(
                    dial_func(conn_info),
                    timeout=remaining,
                )
                probed_principal = await _send_startup_probe(
                    reader,
                    writer,
                    user,
                    database,
                    max(0.0, deadline - loop.time()),
                    conn_name,
                )
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    f"['{conn_name}']: Probing IAM token refresh for ({user}, {database}) failed: {e!s}"
                )
        else:
            for target in targets:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    logger.debug(
                        f"['{conn_name}']: Probing IAM token refresh on {target}:{SERVER_PROXY_PORT}"
                    )
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(
                            host=target,
                            port=SERVER_PROXY_PORT,
                            ssl=ssl_context,
                            server_hostname=(
                                conn_name.domain_name
                                if conn_name.domain_name
                                else None
                            ),
                        ),
                        timeout=remaining,
                    )
                    probed_principal = await _send_startup_probe(
                        reader,
                        writer,
                        user,
                        database,
                        max(0.0, deadline - loop.time()),
                        conn_name,
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    logger.debug(
                        f"['{conn_name}']: Probing IAM token refresh on {target}:{SERVER_PROXY_PORT} failed: {e!s}"
                    )
        if not probed_principal:
            all_succeeded = False

    if all_succeeded:
        logger.debug(
            f"['{conn_name}']: Proactive IAM token refresh probe successful"
        )
    else:
        logger.debug(
            f"['{conn_name}']: Proactive IAM token refresh probe encountered error across all targets"
        )


async def _send_startup_probe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    user: str,
    database: str,
    timeout: float,
    conn_name: ConnectionName,
) -> bool:
    """Sends a PostgreSQL StartupMessage probe and gracefully terminates."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, float(timeout))
    try:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        writer.write(build_postgres_startup_packet(user, database))
        await asyncio.wait_for(writer.drain(), timeout=remaining)
        await asyncio.wait_for(
            reader.read(1024),
            timeout=max(0.0, deadline - loop.time()),
        )
        writer.write(build_terminate_packet())
        await asyncio.wait_for(
            writer.drain(),
            timeout=max(0.0, deadline - loop.time()),
        )
        eof_timeout = min(max(0.0, deadline - loop.time()), 1.0)
        if eof_timeout > 0:
            try:
                await asyncio.wait_for(reader.read(1024), timeout=eof_timeout)
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    f"['{conn_name}']: Ignoring error while waiting for server EOF: {e!s}"
                )
        return True
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
        except Exception as e:  # noqa: BLE001
            logger.debug(
                f"['{conn_name}']: Ignoring error while waiting for socket to close: {e!s}"
            )
            transport = getattr(writer, "transport", None)
            if transport is not None and hasattr(transport, "abort"):
                transport.abort()
