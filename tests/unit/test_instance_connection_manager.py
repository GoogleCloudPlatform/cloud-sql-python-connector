""""
Copyright 2019 Google LLC

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
import pytest  # noqa F401 Needed to run the tests
from google.cloud.sql.connector.instance_connection_manager import (
    InstanceConnectionManager,
)
from google.cloud.sql.connector.utils import generate_keys
import google.auth
import aiohttp


def test_InstanceConnectionManager_init(async_loop):
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """

    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)
    project_result = icm._project
    region_result = icm._region
    instance_result = icm._instance

    del icm

    assert (
        project_result == "test-project"
        and region_result == "test-region"
        and instance_result == "test-instance"
    )


# def test_InstanceConnectionManager_wrong_connection_string():
# """
# Test to check whether the __init__() method of InstanceConnectionManager
# can tell if the connection string that's passed in is formatted correctly.
# """
# loop = asyncio.new_event_loop()
# thr = threading.Thread(target=loop.run_forever)
# thr.start()
# icm = None
# with pytest.raises(CloudSQLConnectionError):
# icm = InstanceConnectionManager("test-project:test-region", loop)

# del icm


@pytest.mark.asyncio
async def test_InstanceConnectionManager_get_ephemeral(connect_string):
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
    priv, pub_key = await generate_keys()

    async with aiohttp.ClientSession() as client_session:
        result = await InstanceConnectionManager._get_ephemeral(
            client_session, credentials, project, instance, pub_key
        )

    result = result.split("\n")

    assert (
        result[0] == "-----BEGIN CERTIFICATE-----"
        and result[len(result) - 1] == "-----END CERTIFICATE-----"
    )


@pytest.mark.asyncio
async def test_InstanceConnectionManager_get_metadata(connect_string):
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
    priv, pub_key = await generate_keys()

    async with aiohttp.ClientSession() as client_session:
        result = await InstanceConnectionManager._get_metadata(
            client_session, credentials, project, instance
        )

    assert result["ip_addresses"] is not None and isinstance(
        result["server_ca_cert"], str
    )


@pytest.mark.asyncio
async def test_InstanceConnectionManager_perform_refresh(async_loop, connect_string):
    """
    Test to check whether _get_perform works as described given valid
    conditions.
    """
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)
    fut = icm._perform_refresh()

    del icm

    assert isinstance(task, asyncio.Task)
