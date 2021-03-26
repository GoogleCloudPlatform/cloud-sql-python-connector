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

import aiohttp
import google.auth
import pytest  # noqa F401 Needed to run the tests

from google.cloud.sql.connector.ephemeral import _get_ephemeral
from google.cloud.sql.connector.utils import generate_keys


@pytest.mark.asyncio
async def test_get_ephemeral(connect_string):
    """
    Test to check whether _get_ephemeral runs without problems given a valid
    connection string.
    """

    project = connect_string.split(":")[0]
    instance = connect_string.split(":")[2]

    credentials, project = google.auth.default()
    credentials = credentials.with_scopes(
        [
            "https://www.googleapis.com/auth/sqlservice.admin",
            "https://www.googleapis.com/auth/cloud-platform",
        ]
    )
    _, pub_key = generate_keys()

    async with aiohttp.ClientSession() as client_session:
        result = await _get_ephemeral(
            client_session, credentials, project, instance, pub_key.decode("UTF-8")
        )

    result = result.split("\n")

    assert (
        result[0] == "-----BEGIN CERTIFICATE-----"
        and result[len(result) - 1] == "-----END CERTIFICATE-----"
    )
