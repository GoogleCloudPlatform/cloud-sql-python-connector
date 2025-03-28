# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import logging
import ssl
from typing import Any, Callable, Optional, Union

from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.connection_info import ConnectionInfoCache
from google.cloud.sql.connector.exceptions import CacheClosedError
from google.cloud.sql.connector.instance import RefreshAheadCache
from google.cloud.sql.connector.lazy import LazyRefreshCache
from google.cloud.sql.connector.resolver import DefaultResolver
from google.cloud.sql.connector.resolver import DnsResolver

logger = logging.getLogger(name=__name__)


class MonitoredCache(ConnectionInfoCache):
    def __init__(
        self,
        cache: Union[RefreshAheadCache, LazyRefreshCache],
        failover_period: int,
        resolver: Union[DefaultResolver, DnsResolver],
    ) -> None:
        self.resolver = resolver
        self.cache = cache
        self.domain_name_ticker: Optional[asyncio.Task] = None
        self.sockets: list[ssl.SSLSocket] = []

        # If domain name is configured for instance and failover period is set,
        # poll for DNS record changes.
        if self.cache.conn_name.domain_name and failover_period > 0:
            self.domain_name_ticker = asyncio.create_task(
                ticker(failover_period, self._check_domain_name)
            )
            logger.debug(
                f"['{self.cache.conn_name}']: Configured polling of domain "
                f"name with failover period of {failover_period} seconds."
            )

    @property
    def closed(self) -> bool:
        return self.cache.closed

    def _purge_closed_sockets(self) -> None:
        """Remove closed sockets from monitored cache.

        If a socket is closed by the database driver we should remove it from
        list of sockets.
        """
        open_sockets = []
        for socket in self.sockets:
            # Check fileno for if socket is closed. Will return
            # -1 on failure, which will be used to signal socket closed.
            if socket.fileno() != -1:
                open_sockets.append(socket)
        self.sockets = open_sockets

    async def _check_domain_name(self) -> None:
        # remove any closed connections from cache
        self._purge_closed_sockets()
        try:
            # Resolve domain name and see if Cloud SQL instance connection name
            # has changed. If it has, close all connections.
            new_conn_name = await self.resolver.resolve(
                self.cache.conn_name.domain_name
            )
            if new_conn_name != self.cache.conn_name:
                logger.debug(
                    f"['{self.cache.conn_name}']: Cloud SQL instance changed "
                    f"from {self.cache.conn_name.get_connection_string()} to "
                    f"{new_conn_name.get_connection_string()}, closing all "
                    "connections!"
                )
                await self.close()

        except Exception as e:
            # Domain name checks should not be fatal, log error and continue.
            logger.debug(
                f"['{self.cache.conn_name}']: Unable to check domain name, "
                f"domain name {self.cache.conn_name.domain_name} did not "
                f"resolve: {e}"
            )

    async def connect_info(self) -> ConnectionInfo:
        if self.closed:
            raise CacheClosedError(
                "Can not get connection info, cache has already been closed."
            )
        return await self.cache.connect_info()

    async def force_refresh(self) -> None:
        # if cache is closed do not refresh
        if self.closed:
            return
        return await self.cache.force_refresh()

    async def close(self) -> None:
        # Cancel domain name ticker task.
        if self.domain_name_ticker:
            self.domain_name_ticker.cancel()
            try:
                await self.domain_name_ticker
            except asyncio.CancelledError:
                logger.debug(
                    f"['{self.cache.conn_name}']: Cancelled domain name polling task."
                )
            finally:
                self.domain_name_ticker = None
        # If cache is already closed, no further work.
        if self.closed:
            return

        # Close underyling ConnectionInfoCache
        await self.cache.close()

        # Close any still open sockets
        for socket in self.sockets:
            # Check fileno for if socket is closed. Will return
            # -1 on failure, which will be used to signal socket closed.
            if socket.fileno() != -1:
                socket.close()


async def ticker(interval: int, function: Callable, *args: Any, **kwargs: Any) -> None:
    """
    Ticker function to sleep for specified interval and then schedule call
    to given function.
    """
    while True:
        # Sleep for interval and then schedule task
        await asyncio.sleep(interval)
        asyncio.create_task(function(*args, **kwargs))
