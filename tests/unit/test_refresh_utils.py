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
from typing import Any

import aiohttp
from google.auth.credentials import Credentials
import json
import pytest  # noqa F401 Needed to run the tests
from mock import AsyncMock, Mock, patch

from google.cloud.sql.connector.refresh_utils import _get_ephemeral, _get_metadata
from google.cloud.sql.connector.utils import generate_keys


class FakeClientSessionGet:
    """Helper class to return mock data for get request."""

    async def text(self):
        response = {
            "kind": "sql#connectSettings",
            "serverCaCert": {
                "kind": "sql#sslCert",
                "certSerialNumber": "0",
                "cert": "-----BEGIN CERTIFICATE-----\nabc123\n-----END CERTIFICATE-----",
                "commonName": "Google",
                "sha1Fingerprint": "abc",
                "instance": "my-instance",
                "createTime": "2021-10-18T18:48:03.785Z",
                "expirationTime": "2031-10-16T18:49:03.785Z",
            },
            "ipAddresses": [
                {"type": "PRIMARY", "ipAddress": "0.0.0.0"},
                {"type": "PRIVATE", "ipAddress": "1.0.0.0"},
            ],
            "region": "my-region",
            "databaseVersion": "MYSQL_8_0",
            "backendType": "SECOND_GEN",
        }
        return json.dumps(response)


class FakeClientSessionPost:
    """Helper class to return mock data for post request."""

    async def text(self):
        response = {
            "ephemeralCert": {
                "kind": "sql#sslCert",
                "certSerialNumber": "",
                "cert": "-----BEGIN CERTIFICATE-----\nabc123\n-----END CERTIFICATE-----",
            }
        }
        return json.dumps(response)


@pytest.fixture
def credentials() -> Credentials:
    credentials = Mock(spec=Credentials)
    credentials.valid = True
    credentials.token = "12345"
    return credentials


@pytest.mark.asyncio
@patch("aiohttp.ClientSession.post", new_callable=AsyncMock)
async def test_get_ephemeral(mock_post: AsyncMock, credentials: Credentials) -> None:
    """
    Test to check whether _get_ephemeral runs without problems given valid
    parameters.
    """
    mock_post.return_value = FakeClientSessionPost()

    project = "my-project"
    instance = "my-instance"

    _, pub_key = await generate_keys()

    async with aiohttp.ClientSession() as client_session:
        result: Any = await _get_ephemeral(
            client_session, credentials, project, instance, pub_key
        )

    result = result.split("\n")

    assert (
        result[0] == "-----BEGIN CERTIFICATE-----"
        and result[len(result) - 1] == "-----END CERTIFICATE-----"
    )


@pytest.mark.asyncio
@patch("aiohttp.ClientSession.get", new_callable=AsyncMock)
async def test_get_metadata(mock_get: AsyncMock, credentials: Credentials) -> None:
    """
    Test to check whether _get_metadata runs without problems given valid
    parameters.
    """
    mock_get.return_value = FakeClientSessionGet()

    project = "my-project"
    instance = "my-instance"

    async with aiohttp.ClientSession() as client_session:
        result = await _get_metadata(client_session, credentials, project, instance)

    assert result["ip_addresses"] is not None and isinstance(
        result["server_ca_cert"], str
    )
