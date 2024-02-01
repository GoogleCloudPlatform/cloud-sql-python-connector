"""
Copyright 2021 Google LLC

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
import asyncio
import datetime
from typing import Any, no_type_check

import aiohttp
from aioresponses import aioresponses
from conftest import SCOPES  # type: ignore
import google.auth
from google.auth.credentials import Credentials
import google.oauth2.credentials
from mock import Mock
from mock import patch
from mocks import FakeCSQLInstance  # type: ignore
from mocks import instance_metadata_expired
from mocks import instance_metadata_success
import pytest  # noqa F401 Needed to run the tests

from google.cloud.sql.connector.refresh_utils import _downscope_credentials
from google.cloud.sql.connector.refresh_utils import _get_ephemeral
from google.cloud.sql.connector.refresh_utils import _get_metadata
from google.cloud.sql.connector.refresh_utils import _is_valid
from google.cloud.sql.connector.refresh_utils import _seconds_until_refresh
from google.cloud.sql.connector.utils import generate_keys


@pytest.fixture
def credentials() -> Credentials:
    credentials = Mock(spec=Credentials)
    credentials.valid = True
    credentials.token = "12345"
    return credentials


@pytest.mark.asyncio
async def test_get_ephemeral(
    mock_instance: FakeCSQLInstance, credentials: Credentials
) -> None:
    """
    Test to check whether _get_ephemeral runs without problems given valid
    parameters.
    """
    project = "my-project"
    instance = "my-instance"
    _, pub_key = await generate_keys()
    # mock Cloud SQL Admin API call
    with aioresponses() as mocked:
        mocked.post(
            "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance:generateEphemeralCert",
            status=200,
            body=mock_instance.generate_ephemeral(pub_key),
            repeat=True,
        )
        async with aiohttp.ClientSession() as client_session:
            result: Any = await _get_ephemeral(
                client_session,
                "https://sqladmin.googleapis.com",
                credentials,
                project,
                instance,
                pub_key,
            )
    cert, _ = result
    cert = cert.strip()  # remove any trailing whitespace
    cert = cert.split("\n")

    assert (
        cert[0] == "-----BEGIN CERTIFICATE-----"
        and cert[len(cert) - 1] == "-----END CERTIFICATE-----"
    )


@pytest.mark.asyncio
@no_type_check
async def test_get_ephemeral_TypeError(credentials: Credentials) -> None:
    """
    Test to check whether _get_ephemeral throws proper TypeError
    when given incorrect input arg types.
    """
    client_session = Mock(aiohttp.ClientSession)
    project = "my-project"
    instance = "my-instance"
    pub_key = "key"

    # incorrect project type
    with pytest.raises(TypeError):
        await _get_ephemeral(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials=credentials,
            project=12345,
            instance=instance,
            pub_key=pub_key,
        )
    # incorrect instance type
    with pytest.raises(TypeError):
        await _get_ephemeral(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials=credentials,
            project=project,
            instance=12345,
            pub_key=pub_key,
        )
    # incorrect pub_key type
    with pytest.raises(TypeError):
        await _get_ephemeral(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials=credentials,
            project=project,
            instance=instance,
            pub_key=12345,
        )


@pytest.mark.asyncio
async def test_get_metadata(
    mock_instance: FakeCSQLInstance, credentials: Credentials
) -> None:
    """
    Test to check whether _get_metadata runs without problems given valid
    parameters.
    """
    project = "my-project"
    region = "my-region"
    instance = "my-instance"
    # mock Cloud SQL Admin API call
    with aioresponses() as mocked:
        mocked.get(
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{project}/instances/{instance}/connectSettings",
            status=200,
            body=mock_instance.connect_settings(),
            repeat=True,
        )

        async with aiohttp.ClientSession() as client_session:
            result = await _get_metadata(
                client_session,
                "https://sqladmin.googleapis.com",
                credentials,
                project,
                region,
                instance,
            )

    assert (
        result["ip_addresses"] is not None
        and result["database_version"] == "POSTGRES_14"
        and isinstance(result["server_ca_cert"], str)
    )


@pytest.mark.asyncio
@no_type_check
async def test_get_metadata_TypeError(credentials: Credentials) -> None:
    """
    Test to check whether _get_metadata throws proper TypeError
    when given incorrect input arg types.
    """
    client_session = Mock(aiohttp.ClientSession)
    project = "my-project"
    region = "my-region"
    instance = "my-instance"

    # incorrect project type
    with pytest.raises(TypeError):
        await _get_metadata(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials=credentials,
            project=12345,
            region=region,
            instance=instance,
        )
    # incorrect region type
    with pytest.raises(TypeError):
        await _get_metadata(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials=credentials,
            project=project,
            region=1,
            instance=instance,
        )
    # incorrect instance type
    with pytest.raises(TypeError):
        await _get_metadata(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials=credentials,
            project=project,
            region=region,
            instance=12345,
        )


@pytest.mark.asyncio
@no_type_check
async def test_get_metadata_region_mismatch(
    mock_instance: FakeCSQLInstance, credentials: Credentials
) -> None:
    """
    Test to check whether _get_metadata throws proper ValueError
    when given mismatched region.
    """
    client_session = Mock(aiohttp.ClientSession)
    project = "my-project"
    region = "bad-region"
    instance = "my-instance"

    # mock Cloud SQL Admin API call
    with aioresponses() as mocked:
        mocked.get(
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{project}/instances/{instance}/connectSettings",
            status=200,
            body=mock_instance.connect_settings(),
            repeat=True,
        )

        async with aiohttp.ClientSession() as client_session:
            with pytest.raises(ValueError):
                await _get_metadata(
                    client_session=client_session,
                    sqladmin_api_endpoint="https://sqladmin.googleapis.com",
                    credentials=credentials,
                    project=project,
                    region=region,
                    instance=instance,
                )


@pytest.mark.asyncio
@no_type_check
async def test_is_valid_with_valid_metadata() -> None:
    """
    Test to check that valid metadata with expiration in future returns True.
    """
    # task that returns class with expiration 10 mins in future
    task = asyncio.create_task(instance_metadata_success())
    assert await _is_valid(task)


@pytest.mark.asyncio
@no_type_check
async def test_is_valid_with_expired_metadata() -> None:
    """
    Test to check that invalid metadata with expiration in past returns False.
    """
    # task that returns class with expiration 10 mins in past
    task = asyncio.create_task(instance_metadata_expired())
    assert not await _is_valid(task)


def test_downscope_credentials_user() -> None:
    """
    Test _downscope_credentials with google.oauth2.credentials.Credentials
    which mimics an authenticated user.
    """
    creds = google.oauth2.credentials.Credentials("token", scopes=SCOPES)
    # override actual refresh URI
    with patch.object(
        google.oauth2.credentials.Credentials, "refresh", lambda *args: None
    ):
        credentials = _downscope_credentials(creds)
    # verify default credential scopes have not been altered
    assert creds.scopes == SCOPES
    # verify downscoped credentials have new scope
    assert credentials.scopes == ["https://www.googleapis.com/auth/sqlservice.login"]
    assert credentials != creds


def test_seconds_until_refresh_over_1_hour() -> None:
    """
    Test _seconds_until_refresh returns proper time in seconds.

    If expiration is over 1 hour, should return duration/2.
    """
    # using pytest.approx since sometimes can be off by a second
    assert (
        pytest.approx(
            _seconds_until_refresh(
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=62)
            ),
            1,
        )
        == 31 * 60
    )


def test_seconds_until_refresh_under_1_hour_over_4_mins() -> None:
    """
    Test _seconds_until_refresh returns proper time in seconds.

    If expiration is under 1 hour and over 4 minutes,
    should return duration-refresh_buffer (refresh_buffer = 4 minutes).
    """
    # using pytest.approx since sometimes can be off by a second
    assert (
        pytest.approx(
            _seconds_until_refresh(
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=5)
            ),
            1,
        )
        == 60
    )


def test_seconds_until_refresh_under_4_mins() -> None:
    """
    Test _seconds_until_refresh returns proper time in seconds.

    If expiration is under 4 minutes, should return 0.
    """
    assert (
        _seconds_until_refresh(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=3)
        )
        == 0
    )
