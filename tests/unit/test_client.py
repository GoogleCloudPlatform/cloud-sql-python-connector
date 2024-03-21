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

import datetime
from typing import Optional

from mocks import FakeCredentials
import pytest

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.utils import generate_keys
from google.cloud.sql.connector.version import __version__ as version


@pytest.mark.asyncio
async def test_get_metadata(fake_client: CloudSQLClient) -> None:
    """
    Test _get_metadata returns successfully.
    """
    resp = await fake_client._get_metadata(
        "test-project",
        "test-region",
        "test-instance",
    )
    assert resp["database_version"] == "POSTGRES_15"
    assert resp["ip_addresses"] == {
        "PRIMARY": "127.0.0.1",
        "PRIVATE": "10.0.0.1",
        "PSC": "abcde.12345.us-central1.sql.goog",
    }
    assert isinstance(resp["server_ca_cert"], str)


@pytest.mark.asyncio
async def test_get_ephemeral(fake_client: CloudSQLClient) -> None:
    """
    Test _get_ephemeral returns successfully.
    """
    keys = await generate_keys()
    client_cert, expiration = await fake_client._get_ephemeral(
        "test-project", "test-instance", keys[1]
    )
    assert isinstance(client_cert, str)
    assert expiration > datetime.datetime.now(datetime.timezone.utc)


@pytest.mark.asyncio
async def test_CloudSQLClient_init_(fake_credentials: FakeCredentials) -> None:
    """
    Test to check whether the __init__ method of CloudSQLClient
    can correctly initialize a client.
    """
    driver = "pg8000"
    client = CloudSQLClient(
        "www.test-endpoint.com", "my-quota-project", fake_credentials, driver=driver
    )
    # verify base endpoint is set
    assert client._sqladmin_api_endpoint == "www.test-endpoint.com"
    # verify proper headers are set
    assert (
        client._client.headers["User-Agent"]
        == f"cloud-sql-python-connector/{version}+{driver}"
    )
    assert client._client.headers["x-goog-user-project"] == "my-quota-project"
    # close client
    await client.close()


@pytest.mark.asyncio
async def test_CloudSQLClient_init_custom_user_agent(
    fake_credentials: FakeCredentials,
) -> None:
    """
    Test to check that custom user agents are included in HTTP requests.
    """
    client = CloudSQLClient(
        "www.test-endpoint.com",
        "my-quota-project",
        fake_credentials,
        user_agent="custom-agent/v1.0.0 other-agent/v2.0.0",
    )
    assert (
        client._client.headers["User-Agent"]
        == f"cloud-sql-python-connector/{version} custom-agent/v1.0.0 other-agent/v2.0.0"
    )
    await client.close()


@pytest.mark.parametrize(
    "driver",
    [None, "pg8000", "asyncpg", "pymysql", "pytds"],
)
@pytest.mark.asyncio
async def test_CloudSQLClient_user_agent(
    driver: Optional[str], fake_credentials: FakeCredentials
) -> None:
    """
    Test to check whether the __init__ method of CloudSQLClient
    properly sets user agent when passed a database driver.
    """
    client = CloudSQLClient(
        "www.test-endpoint.com", "my-quota-project", fake_credentials, driver=driver
    )
    if driver is None:
        assert client._user_agent == f"cloud-sql-python-connector/{version}"
    else:
        assert client._user_agent == f"cloud-sql-python-connector/{version}+{driver}"
    # close client
    await client.close()
