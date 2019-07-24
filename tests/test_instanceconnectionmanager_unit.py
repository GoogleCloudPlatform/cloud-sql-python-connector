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

import pytest
import aiohttp
from google.cloud.sql.connector.InstanceConnectionManager import (
    InstanceConnectionManager,
    CloudSQLConnectionError,
)
import asyncio
import os
import concurrent
import threading


def thread_looper(loop):
    try:
        loop.run_forever()
    finally:
        loop.stop()


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
    # loop.stop()
    # thr.run(loop.stop())

    assert (
        icm._project == "test-project"
        and icm._region == "test-region"
        and icm._instance == "test-instance"
    )


def test_InstanceConnectionManager_wrong_connection_string():
    """
    Test to check whether the __init__() method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """
    loop = asyncio.new_event_loop()
    thr = threading.Thread(target=loop.run_forever)
    thr.start()
    with pytest.raises(CloudSQLConnectionError):
        InstanceConnectionManager("test-project:test-region", loop)
        loop.stop()


def test_InstanceConnectionManager_get_ephemeral():
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

    loop = asyncio.new_event_loop()
    thr = threading.Thread(target=loop.run_forever)
    thr.start()
    icm = InstanceConnectionManager(connect_string, loop)

    async def async_get_ephemeral():
        async with aiohttp.ClientSession() as client_session:
            return await icm._get_ephemeral(
                client_session,
                icm._credentials,
                icm._project,
                icm._instance,
                icm._pub_key.decode("UTF-8"),
            )

    fut = asyncio.run_coroutine_threadsafe(async_get_ephemeral(), loop=loop)
    # icm._loop.close()
    # thr.join()

    result = fut.result().split("\n")
    loop.stop()

    assert (
        result[0] == "-----BEGIN CERTIFICATE-----"
        and result[len(result) - 1] == "-----END CERTIFICATE-----"
    )


def test_InstanceConnectionManager_get_metadata():
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

    loop = asyncio.new_event_loop()
    thr = threading.Thread(target=loop.run_forever, daemon=True)
    thr.start()
    icm = InstanceConnectionManager(connect_string, loop)

    async def async_get_metadata():
        async with aiohttp.ClientSession() as client_session:
            return await icm._get_metadata(
                client_session, icm._credentials, icm._project, icm._instance
            )

    fut = asyncio.run_coroutine_threadsafe(async_get_metadata(), loop=loop)

    result = fut.result()
    # thr.join(timeout=10)
    loop.stop()
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

    # thr.join(timeout=20)
    loop.stop()
    assert isinstance(fut, concurrent.futures.Future)
