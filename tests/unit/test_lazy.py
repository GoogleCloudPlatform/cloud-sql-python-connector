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

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.lazy import LazyRefreshCache
from google.cloud.sql.connector.utils import generate_keys


async def test_LazyRefreshCache_connect_info(fake_client: CloudSQLClient) -> None:
    """
    Test that LazyRefreshCache.connect_info works as expected.
    """
    keys = asyncio.create_task(generate_keys())
    cache = LazyRefreshCache(
        ConnectionName("test-project", "test-region", "test-instance"),
        client=fake_client,
        keys=keys,
        enable_iam_auth=False,
    )
    # check that cached connection info is empty
    assert cache._cached is None
    conn_info = await cache.connect_info()
    # check that cached connection info is now set
    assert isinstance(cache._cached, ConnectionInfo)
    # check that calling connect_info uses cached info
    conn_info2 = await cache.connect_info()
    assert conn_info2 == conn_info


async def test_LazyRefreshCache_force_refresh(fake_client: CloudSQLClient) -> None:
    """
    Test that LazyRefreshCache.force_refresh works as expected.
    """
    keys = asyncio.create_task(generate_keys())
    cache = LazyRefreshCache(
        ConnectionName("test-project", "test-region", "test-instance"),
        client=fake_client,
        keys=keys,
        enable_iam_auth=False,
    )
    conn_info = await cache.connect_info()
    # check that cached connection info is now set
    assert isinstance(cache._cached, ConnectionInfo)
    await cache.force_refresh()
    # check that calling connect_info after force_refresh gets new ConnectionInfo
    conn_info2 = await cache.connect_info()
    # check that new connection info was retrieved
    assert conn_info2 != conn_info
    assert cache._cached == conn_info2
    await cache.close()
