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
from unittest.mock import AsyncMock

import pytest

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.lazy import LazyRefreshCache
from google.cloud.sql.connector.utils import generate_keys


async def test_LazyRefreshCache_properties(fake_client: CloudSQLClient) -> None:
    """
    Test that LazyRefreshCache properties work as expected.
    """
    keys = asyncio.create_task(generate_keys())
    conn_name = ConnectionName("test-project", "test-region", "test-instance")
    cache = LazyRefreshCache(
        conn_name,
        client=fake_client,
        keys=keys,
        enable_iam_auth=False,
    )
    # test conn_name property
    assert cache.conn_name == conn_name
    # test closed property
    assert cache.closed is False
    # close cache and make sure property is updated
    await cache.close()
    assert cache.closed is True


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


async def test_LazyRefreshCache_connect_info_error(
    fake_client: CloudSQLClient,
) -> None:
    """
    Test that LazyRefreshCache.connect_info propagates exceptions.
    """
    keys = asyncio.create_task(generate_keys())
    cache = LazyRefreshCache(
        ConnectionName("test-project", "test-region", "test-instance"),
        client=fake_client,
        keys=keys,
        enable_iam_auth=False,
    )

    # Mock get_connection_info to raise an exception
    fake_client.get_connection_info = AsyncMock(side_effect=Exception("Test Exception"))

    with pytest.raises(Exception, match="Test Exception"):
        await cache.connect_info()

    await cache.close()


async def test_LazyRefreshCache_probe_connection_postgres_startup_packet(
    fake_client: CloudSQLClient,
) -> None:
    """
    Test that LazyRefreshCache.connect_info probes the instance with a PostgreSQL
    StartupMessage and Terminate when enable_iam_auth=True and a principal is recorded.
    """
    from unittest.mock import MagicMock, patch
    from google.cloud.sql.connector.instance import _build_postgres_startup_packet

    keys = asyncio.create_task(generate_keys())
    cache = LazyRefreshCache(
        ConnectionName("test-project", "test-region", "test-instance"),
        client=fake_client,
        keys=keys,
        enable_iam_auth=True,
    )
    cache.record_principal("iam-user@example.com", "mydb")

    mock_reader = AsyncMock()
    mock_reader.read = AsyncMock(return_value=b"R\x00\x00\x00\x08\x00\x00\x00\x00")
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.wait_closed = AsyncMock()

    with patch(
        "google.cloud.sql.connector.instance.asyncio.open_connection",
        AsyncMock(return_value=(mock_reader, mock_writer)),
    ) as mock_open_conn:
        await cache.connect_info()

    mock_open_conn.assert_awaited_once()
    written_packets = [call.args[0] for call in mock_writer.write.call_args_list]
    expected_startup = _build_postgres_startup_packet("iam-user@example.com", "mydb")
    assert written_packets == [expected_startup, b"X\x00\x00\x00\x04"]
    mock_reader.read.assert_awaited_once()
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_awaited_once()
    await cache.close()


