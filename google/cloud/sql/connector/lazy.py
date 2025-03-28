# Copyright 2024 Google LLC
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
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import logging
from typing import Optional

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.connection_info import ConnectionInfoCache
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.refresh_utils import _refresh_buffer

logger = logging.getLogger(name=__name__)


class LazyRefreshCache(ConnectionInfoCache):
    """Cache that refreshes connection info when a caller requests a connection.

    Only refreshes the cache when a new connection is requested and the current
    certificate is close to or already expired.

    This is the recommended option for serverless environments.
    """

    def __init__(
        self,
        conn_name: ConnectionName,
        client: CloudSQLClient,
        keys: asyncio.Future,
        enable_iam_auth: bool = False,
    ) -> None:
        """Initializes a LazyRefreshCache instance.

        Args:
            conn_name (ConnectionName): The Cloud SQL instance's
                connection name.
            client (CloudSQLClient): The Cloud SQL Client instance.
            keys (asyncio.Future): A future to the client's public-private key
                pair.
            enable_iam_auth (bool): Enables automatic IAM database authentication
                (Postgres and MySQL) as the default authentication method for all
                connections.
        """
        self._conn_name = conn_name
        self._enable_iam_auth = enable_iam_auth
        self._keys = keys
        self._client = client
        self._lock = asyncio.Lock()
        self._cached: Optional[ConnectionInfo] = None
        self._needs_refresh = False
        self._closed = False

    @property
    def conn_name(self) -> ConnectionName:
        return self._conn_name

    @property
    def closed(self) -> bool:
        return self._closed

    async def force_refresh(self) -> None:
        """
        Invalidates the cache and configures the next call to
        connect_info() to retrieve a fresh ConnectionInfo instance.
        """
        async with self._lock:
            self._needs_refresh = True

    async def connect_info(self) -> ConnectionInfo:
        """Retrieves ConnectionInfo instance for establishing a secure
        connection to the Cloud SQL instance.
        """
        async with self._lock:
            # If connection info is cached, check expiration.
            # Pad expiration with a buffer to give the client plenty of time to
            # establish a connection to the server with the certificate.
            if (
                self._cached
                and not self._needs_refresh
                and datetime.now(timezone.utc)
                < (self._cached.expiration - timedelta(seconds=_refresh_buffer))
            ):
                logger.debug(
                    f"['{self._conn_name}']: Connection info "
                    "is still valid, using cached info"
                )
                return self._cached
            logger.debug(
                f"['{self._conn_name}']: Connection info " "refresh operation started"
            )
            try:
                conn_info = await self._client.get_connection_info(
                    self._conn_name,
                    self._keys,
                    self._enable_iam_auth,
                )
            except Exception as e:
                logger.debug(
                    f"['{self._conn_name}']: Connection info "
                    f"refresh operation failed: {str(e)}"
                )
                raise
            logger.debug(
                f"['{self._conn_name}']: Connection info "
                "refresh operation completed successfully"
            )
            logger.debug(
                f"['{self._conn_name}']: Current certificate "
                f"expiration = {str(conn_info.expiration)}"
            )
            self._cached = conn_info
            self._needs_refresh = False
            return conn_info

    async def close(self) -> None:
        """Close is a no-op and provided purely for a consistent interface with
        other cache types.
        """
        self._closed = True
        return
