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

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from aiohttp import ClientResponseError
from aioresponses import aioresponses
from google.auth.credentials import Credentials
from google.auth.credentials import TokenState
from mocks import FakeCredentials
import pytest

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.client import DEFAULT_SERVICE_ENDPOINT
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
        "PRIMARY": ["127.0.0.1"],
        "PRIVATE": ["10.0.0.1"],
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
        "PRIMARY": ["127.0.0.1"],
        "PRIVATE": ["10.0.0.1"],
        "PSC": ["abcde.12345.us-central1.sql.goog"],
    }
    assert isinstance(resp["server_ca_cert"], str)


@pytest.mark.asyncio
async def test_get_metadata_legacy_dns_with_psc(fake_client: CloudSQLClient) -> None:
    """
    Test _get_metadata returns successfully with PSC IP type.
    """
    # set PSC to enabled on test instance
    fake_client.instance.psc_enabled = True
    fake_client.instance.legacy_dns_name = True
    resp = await fake_client._get_metadata(
        "test-project",
        "test-region",
        "test-instance",
    )
    assert resp["database_version"] == "POSTGRES_15"
    assert resp["ip_addresses"] == {
        "PRIMARY": ["127.0.0.1"],
        "PRIVATE": ["10.0.0.1"],
        "PSC": ["abcde.12345.us-central1.sql.goog"],
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
    driver: str | None, fake_credentials: FakeCredentials
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


async def test_get_metadata_error_parsing_json(
    fake_credentials: Credentials,
) -> None:
    """
    Test that aiohttp default error messages are raised when _get_metadata gets
    a bad JSON response.
    """
    # mock Cloud SQL Admin API calls with exceptions
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance/connectSettings"
    resp_body = ["error"]  # invalid JSON
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
        assert exc_info.value.message == "Forbidden"
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


async def test_get_ephemeral_error_parsing_json(
    fake_credentials: Credentials,
) -> None:
    """
    Test that aiohttp default error messages are raised when _get_ephemeral gets
    a bad JSON response.
    """
    # mock Cloud SQL Admin API calls with exceptions
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    post_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance:generateEphemeralCert"
    resp_body = ["error"]  # invalid JSON
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
        assert exc_info.value.message == "Not Found"
        await client.close()


@pytest.mark.asyncio
async def test_get_metadata_multiple_psc_dns_sorted(fake_client: CloudSQLClient) -> None:
    """
    Test _get_metadata returns successfully with multiple PSC IP types sorted.
    """
    fake_client.instance.psc_enabled = True
    fake_client.instance.legacy_dns_name = False
    fake_client.instance.dns_names = [
        "dns1.sql.goog",
        "dns2.sql-psc.goog",
        "dns3.sql.goog",
    ]
    try:
        resp = await fake_client._get_metadata(
            "test-project",
            "test-region",
            "test-instance",
        )
        assert resp["database_version"] == "POSTGRES_15"
        assert resp["ip_addresses"] == {
            "PRIMARY": ["127.0.0.1"],
            "PRIVATE": ["10.0.0.1"],
            "PSC": ["dns2.sql-psc.goog", "dns1.sql.goog", "dns3.sql.goog"],
        }
        assert isinstance(resp["server_ca_cert"], str)
    finally:
        fake_client.instance.psc_enabled = False
        fake_client.instance.legacy_dns_name = False
        fake_client.instance.dns_names = ["abcde.12345.us-central1.sql.goog"]


@pytest.mark.asyncio
async def test_get_metadata_multiple_psc_dns_sorted_with_trailing_dots(
    fake_client: CloudSQLClient,
) -> None:
    """
    Test _get_metadata returns successfully with multiple PSC IP types sorted
    even when names contain trailing dots or mixed case.
    """
    fake_client.instance.psc_enabled = True
    fake_client.instance.legacy_dns_name = False
    fake_client.instance.dns_names = [
        "dns1.sql.goog.",
        "dns2.SQL-PSC.GOOG.",
        "dns3.sql.goog.",
    ]
    try:
        resp = await fake_client._get_metadata(
            "test-project",
            "test-region",
            "test-instance",
        )
        assert resp["database_version"] == "POSTGRES_15"
        assert resp["ip_addresses"] == {
            "PRIMARY": ["127.0.0.1"],
            "PRIVATE": ["10.0.0.1"],
            "PSC": ["dns2.SQL-PSC.GOOG", "dns1.sql.goog", "dns3.sql.goog"],
        }
        assert isinstance(resp["server_ca_cert"], str)
    finally:
        fake_client.instance.psc_enabled = False
        fake_client.instance.legacy_dns_name = False
        fake_client.instance.dns_names = ["abcde.12345.us-central1.sql.goog"]



async def test_CloudSQLClient_init_default_endpoint(
    fake_credentials: FakeCredentials,
) -> None:
    """Test that CloudSQLClient uses default endpoint if None is passed."""
    client = CloudSQLClient(None, "my-quota-project", fake_credentials)
    assert client._sqladmin_api_endpoint == DEFAULT_SERVICE_ENDPOINT
    await client.close()


async def test_get_metadata_retry_50x(fake_credentials: Credentials) -> None:
    """Test that _get_metadata retries on 5xx errors."""
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance/connectSettings"

    resp_body = {
        "ipAddresses": [{"type": "PRIMARY", "ipAddress": "127.0.0.1"}],
        "region": "my-region",
        "databaseVersion": "POSTGRES_15",
        "serverCaCert": {"cert": "ca-cert"},
    }

    with aioresponses() as mocked:
        # First call returns 500
        mocked.get(get_url, status=500)
        # Second call returns 200
        mocked.get(get_url, status=200, payload=resp_body)

        # We need to mock sleep in retry_50x to make it fast
        with patch(
            "google.cloud.sql.connector.refresh_utils.asyncio.sleep", AsyncMock()
        ):
            resp = await client._get_metadata("my-project", "my-region", "my-instance")

        assert resp["database_version"] == "POSTGRES_15"
        assert resp["ip_addresses"] == {"PRIMARY": ["127.0.0.1"]}
        await client.close()


async def test_get_ephemeral_retry_50x(fake_credentials: Credentials) -> None:
    """Test that _get_ephemeral retries on 5xx errors."""
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    post_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance:generateEphemeralCert"

    resp_body = {
        "ephemeralCert": {"cert": "ephemeral-cert"},
    }

    mock_x509 = MagicMock()
    mock_x509.not_valid_after_utc = datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(hours=1)

    with aioresponses() as mocked, patch(
        "google.cloud.sql.connector.client.load_pem_x509_certificate",
        return_value=mock_x509,
    ):
        # First call returns 500
        mocked.post(post_url, status=500)
        # Second call returns 200
        mocked.post(post_url, status=200, payload=resp_body)

        # We need to mock sleep in retry_50x to make it fast
        with patch(
            "google.cloud.sql.connector.refresh_utils.asyncio.sleep", AsyncMock()
        ):
            cert, expiration = await client._get_ephemeral(
                "my-project", "my-instance", "pub-key"
            )

        assert cert == "ephemeral-cert"
        assert expiration == mock_x509.not_valid_after_utc
        await client.close()


async def test_get_metadata_region_mismatch(fake_credentials: Credentials) -> None:
    """Test that _get_metadata raises ValueError if region mismatched."""
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance/connectSettings"

    resp_body = {
        "ipAddresses": [{"type": "PRIMARY", "ipAddress": "127.0.0.1"}],
        "region": "wrong-region",
        "databaseVersion": "POSTGRES_15",
        "serverCaCert": {"cert": "ca-cert"},
    }

    with aioresponses() as mocked:
        mocked.get(get_url, status=200, payload=resp_body)
        with pytest.raises(ValueError) as exc_info:
            await client._get_metadata("my-project", "my-region", "my-instance")
        assert "Provided region was mismatched" in str(exc_info.value)
        await client.close()


async def test_resolve_connect_settings_success(fake_credentials: Credentials) -> None:
    """Test resolve_connect_settings returns successfully."""
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/locations/my-region/dns/my-dns:resolveConnectSettings"
    resp_body = {"connectionName": "my-project:my-region:my-instance"}

    with aioresponses() as mocked:
        mocked.get(get_url, status=200, payload=resp_body)
        resp = await client.resolve_connect_settings("my-dns", "my-region")
        assert resp == resp_body
        await client.close()


async def test_resolve_connect_settings_error(fake_credentials: Credentials) -> None:
    """Test resolve_connect_settings raises error on failure."""
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/locations/my-region/dns/my-dns:resolveConnectSettings"
    resp_body = {
        "error": {
            "code": 404,
            "message": "DNS name not found",
        }
    }

    with aioresponses() as mocked:
        mocked.get(get_url, status=404, payload=resp_body)
        with pytest.raises(ClientResponseError) as exc_info:
            await client.resolve_connect_settings("my-dns", "my-region")
        assert exc_info.value.status == 404
        assert exc_info.value.message == "DNS name not found"
        await client.close()


async def test_resolve_connect_settings_retry_50x(fake_credentials: Credentials) -> None:
    """Test that resolve_connect_settings retries on 5xx errors."""
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/locations/my-region/dns/my-dns:resolveConnectSettings"
    resp_body = {"connectionName": "my-project:my-region:my-instance"}

    with aioresponses() as mocked:
        # First call returns 500
        mocked.get(get_url, status=500)
        # Second call returns 200
        mocked.get(get_url, status=200, payload=resp_body)

        with patch(
            "google.cloud.sql.connector.refresh_utils.asyncio.sleep", AsyncMock()
        ):
            resp = await client.resolve_connect_settings("my-dns", "my-region")

        assert resp == resp_body
        await client.close()


async def test_resolve_connect_settings_token_refresh(fake_credentials: FakeCredentials) -> None:
    """Test that resolve_connect_settings refreshes token if it is not FRESH."""
    fake_credentials.token = "expired-token"
    fake_credentials.expiry = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(minutes=10)
    assert fake_credentials.token_state == TokenState.INVALID

    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/locations/my-region/dns/my-dns:resolveConnectSettings"
    resp_body = {"connectionName": "my-project:my-region:my-instance"}

    with aioresponses() as mocked:
        mocked.get(get_url, status=200, payload=resp_body)
        resp = await client.resolve_connect_settings("my-dns", "my-region")

        assert resp == resp_body
        assert fake_credentials.token == "12345"
        await client.close()


async def test_resolve_connect_settings_error_parsing_json(
    fake_credentials: Credentials,
) -> None:
    """Test that aiohttp default error messages are raised when resolve_connect_settings gets a bad JSON response."""
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/locations/my-region/dns/my-dns:resolveConnectSettings"
    resp_body = ["error"]
    with aioresponses() as mocked:
        mocked.get(
            get_url,
            status=403,
            payload=resp_body,
            repeat=True,
        )
        with pytest.raises(ClientResponseError) as exc_info:
            await client.resolve_connect_settings("my-dns", "my-region")
        assert exc_info.value.status == 403
        assert exc_info.value.message == "Forbidden"
        await client.close()




