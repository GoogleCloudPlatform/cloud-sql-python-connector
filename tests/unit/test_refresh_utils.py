""""
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
from typing import Any, no_type_check

import aiohttp
from google.auth.credentials import Credentials
import pytest  # noqa F401 Needed to run the tests
from mock import Mock
from aioresponses import aioresponses
import asyncio

from google.cloud.sql.connector.refresh_utils import (
    _get_ephemeral,
    _get_metadata,
    _is_valid,
)
from google.cloud.sql.connector.utils import generate_keys

# import mocks
from mocks import (  # type: ignore
    instance_metadata_success,
    instance_metadata_expired,
    FakeCSQLInstance,
)


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
    result = result.strip()  # remove any trailing whitespace
    result = result.split("\n")

    assert (
        result[0] == "-----BEGIN CERTIFICATE-----"
        and result[len(result) - 1] == "-----END CERTIFICATE-----"
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

    # incorrect credentials type
    with pytest.raises(TypeError):
        await _get_ephemeral(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials="bad-credentials",
            project=project,
            instance=instance,
            pub_key=pub_key,
        )
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
    instance = "my-instance"
    # mock Cloud SQL Admin API call
    with aioresponses() as mocked:
        mocked.get(
            "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance/connectSettings",
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
    instance = "my-instance"

    # incorrect credentials type
    with pytest.raises(TypeError):
        await _get_metadata(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials="bad-credentials",
            project=project,
            instance=instance,
        )
    # incorrect project type
    with pytest.raises(TypeError):
        await _get_metadata(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials=credentials,
            project=12345,
            instance=instance,
        )
    # incorrect instance type
    with pytest.raises(TypeError):
        await _get_metadata(
            client_session=client_session,
            sqladmin_api_endpoint="https://sqladmin.googleapis.com",
            credentials=credentials,
            project=project,
            instance=12345,
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
