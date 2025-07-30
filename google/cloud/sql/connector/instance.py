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
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import logging

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.connection_info import ConnectionInfoCache
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import RefreshNotValidError
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.cloud.sql.connector.refresh_utils import _is_valid
from google.cloud.sql.connector.refresh_utils import _seconds_until_refresh

logger = logging.getLogger(name=__name__)

APPLICATION_NAME = "cloud-sql-python-connector"


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
        """
        self._conn_name = conn_name

        self._enable_iam_auth = enable_iam_auth
        self._keys = keys
        self._client = client
        self._refresh_rate_limiter = AsyncRateLimiter(
            max_capacity=2,
            rate=1 / 30,
        )
        self._lock = asyncio.Lock()
        self._current: asyncio.Task = self._schedule_refresh(0)
        self._next: asyncio.Task = self._current
        self._closed = False

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
        if not self._lock.locked():
            async with self._lock:
                self._next.cancel()
                self._next = self._schedule_refresh(0)
        # block all sequential connection attempts on the next refresh result if current is invalid
        async with self._lock:
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
