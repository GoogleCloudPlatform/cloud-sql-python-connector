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
from typing import Tuple

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.instance import _parse_instance_connection_name
from google.cloud.sql.connector.instance import ConnectionInfo
from google.cloud.sql.connector.instance import IPTypes


class LazyRefreshCache:
    """Cache that refreshes connection info when a caller requests a connection.

    Only refreshes the cache when a new connection is requested and the current
    certificate is close to or already expired.
    """

    def __init__(
        self,
        instance_connection_string: str,
        client: CloudSQLClient,
        keys: asyncio.Future,
        enable_iam_auth: bool = False,
    ) -> None:
        """Initializes a LazyRefreshCache instance.

        Args:
            instance_connection_string (str): The Cloud SQL Instance's
                connection string (also known as an instance connection name).
            client (CloudSQLClient): The Cloud SQL Client instance.
            keys (asyncio.Future): A future to the client's public-private key
                pair.
            enable_iam_auth (bool): Enables automatic IAM database authentication
                (Postgres and MySQL) as the default authentication method for all
                connections.
        """
        # validate and parse instance connection name
        self._project, self._region, self._instance = _parse_instance_connection_name(
            instance_connection_string
        )
        self._instance_connection_string = instance_connection_string

        self._enable_iam_auth = enable_iam_auth
        self._keys = keys
        self._client = client
        self._refresh_in_progress = asyncio.locks.Event()

    async def force_refresh(self) -> None:
        pass

    async def connect_info(
        self,
        ip_type: IPTypes,
    ) -> Tuple[ConnectionInfo, str]:
        """Retrieve instance metadata and ip address required
        for making connection to Cloud SQL instance.

        Args:
            ip_type (IPTypes): Enum specifying type of IP address to lookup and
                use for connection.

        Returns:
            A tuple with the first item being the ConnectionInfo instance for
            establishing the connection, and the second item being the IP
            address of the Cloud SQL instance matching the specified IP type.
        """

        pass
