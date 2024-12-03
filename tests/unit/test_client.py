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

from aiohttp import ClientResponseError
from aioresponses import aioresponses
from google.auth.credentials import Credentials
from mocks import FakeCredentials
import pytest

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.utils import generate_keys
from google.cloud.sql.connector.version import __version__ as version


@pytest.mark.asyncio
async def test_get_metadata_no_psc(fake_client: CloudSQLClient) -> None:
    """
    Test _get_metadata returns successfully and does not include PSC IP type.
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
    }
    assert isinstance(resp["server_ca_cert"], str)


@pytest.mark.asyncio
async def test_get_metadata_with_psc(fake_client: CloudSQLClient) -> None:
    """
    Test _get_metadata returns successfully with PSC IP type.
    """
    # set PSC to enabled on test instance
    fake_client.instance.psc_enabled = True
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


async def test_cloud_sql_error_messages_get_metadata(
    fake_credentials: Credentials,
) -> None:
    """
    Test that Cloud SQL Admin API error messages are raised for _get_metadata.
    """
    # mock Cloud SQL Admin API calls with exceptions
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance/connectSettings"
    resp_body = {
        "error": {
            "code": 403,
            "message": "Cloud SQL Admin API has not been used in project 123456789 before or it is disabled",
        }
    }
    with aioresponses() as mocked:
        mocked.get(
            get_url,
            status=403,
            payload=resp_body,
            repeat=True,
        )
        with pytest.raises(ClientResponseError) as exc_info:
            await client._get_metadata("my-project", "my-region", "my-instance")
        assert exc_info.value.status == 403
        assert (
            exc_info.value.message
            == "Cloud SQL Admin API has not been used in project 123456789 before or it is disabled"
        )
        await client.close()


async def test_cloud_sql_error_messages_get_ephemeral(
    fake_credentials: Credentials,
) -> None:
    """
    Test that Cloud SQL Admin API error messages are raised for _get_ephemeral.
    """
    # mock Cloud SQL Admin API calls with exceptions
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    post_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance:generateEphemeralCert"
    resp_body = {
        "error": {
            "code": 404,
            "message": "The Cloud SQL instance does not exist.",
        }
    }
    with aioresponses() as mocked:
        mocked.post(
            post_url,
            status=404,
            payload=resp_body,
            repeat=True,
        )
        with pytest.raises(ClientResponseError) as exc_info:
            await client._get_ephemeral("my-project", "my-instance", "my-key")
        assert exc_info.value.status == 404
        assert exc_info.value.message == "The Cloud SQL instance does not exist."
        await client.close()
