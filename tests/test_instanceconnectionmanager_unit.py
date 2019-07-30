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

import pytest  # noqa F401 Needed to run the tests
from google.cloud.sql.connector.InstanceConnectionManager import (
    InstanceConnectionManager,
)
from google.cloud.sql.connector.utils import generate_keys
import asyncio
import os
import threading
import concurrent
import google.auth
import aiohttp


def test_InstanceConnectionManager_init():
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """
    loop = asyncio.new_event_loop()
    thr = threading.Thread(target=loop.run_forever)
    thr.start()
    connect_string = "test-project:test-region:test-instance"
    icm = InstanceConnectionManager(connect_string, loop)
    project_result = icm._project
    region_result = icm._region
    instance_result = icm._instance

    del icm
    loop.call_soon_threadsafe(loop.stop)
    # thr.run(loop.stop())

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
async def test_InstanceConnectionManager_get_ephemeral():
    """
    Test to check whether _get_ephemeral runs without problems given a valid
    connection string.
    """

    try:
        connect_string = os.environ["INSTANCE_CONNECTION_NAME"]
    except KeyError:
        raise KeyError(
            "Please set environment variable 'INSTANCE_CONNECTION"
            + "_NAME' to a valid Cloud SQL connection string."
        )

    project = connect_string.split(":")[0]
    instance = connect_string.split(":")[2]

    credentials, project = google.auth.default()
    credentials = credentials.with_scopes(
        [
            "https://www.googleapis.com/auth/sqlservice.admin",
            "https://www.googleapis.com/auth/cloud-platform",
        ]
    )
    priv, pub_key = generate_keys()

    async with aiohttp.ClientSession() as client_session:
        result = await InstanceConnectionManager._get_ephemeral(
            client_session, credentials, project, instance, pub_key.decode("UTF-8")
        )

    result = result.split("\n")

    assert (
        result[0] == "-----BEGIN CERTIFICATE-----"
        and result[len(result) - 1] == "-----END CERTIFICATE-----"
    )


@pytest.mark.asyncio
async def test_InstanceConnectionManager_get_metadata():
    """
    Test to check whether _get_ephemeral runs without problems given a valid
    connection string.
    """

    try:
        connect_string = os.environ["INSTANCE_CONNECTION_NAME"]
    except KeyError:
        raise KeyError(
            "Please set environment variable 'INSTANCE_CONNECTION"
            + "_NAME' to a valid Cloud SQL connection string."
        )

    project = connect_string.split(":")[0]
    instance = connect_string.split(":")[2]

    credentials, project = google.auth.default()
    credentials = credentials.with_scopes(
        [
            "https://www.googleapis.com/auth/sqlservice.admin",
            "https://www.googleapis.com/auth/cloud-platform",
        ]
    )
    priv, pub_key = generate_keys()

    async with aiohttp.ClientSession() as client_session:
        result = await InstanceConnectionManager._get_metadata(
            client_session, credentials, project, instance
        )

    assert result["ip_addresses"] is not None and isinstance(
        result["server_ca_cert"], str
    )


def test_InstanceConnectionManager_perform_refresh():
    """
    Test to check whether _get_perform works as described given valid
    conditions.
    """
    try:
        connect_string = os.environ["INSTANCE_CONNECTION_NAME"]
    except KeyError:
        raise KeyError(
            "Please set environment variable 'INSTANCE_CONNECTION"
            + "_NAME' to a valid Cloud SQL connection string."
        )

    loop = asyncio.new_event_loop()
    thr = threading.Thread(target=loop.run_forever, daemon=True)
    thr.start()
    icm = InstanceConnectionManager(connect_string, loop)
    fut = icm._perform_refresh()

    del icm
    loop.stop()
    assert isinstance(fut, concurrent.futures.Future)
