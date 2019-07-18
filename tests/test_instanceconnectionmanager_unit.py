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


def test_InstanceConnectionManager_init():
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """
    loop = asyncio.new_event_loop()
    connect_string = "test-project:test-region:test-instance"
    icm = InstanceConnectionManager(connect_string, loop)
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
    with pytest.raises(CloudSQLConnectionError):
        InstanceConnectionManager("test-project:test-region", loop)


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
    icm = InstanceConnectionManager(connect_string, loop)

    async def create_client_session():
        return aiohttp.ClientSession()

    fut_client_session = asyncio.ensure_future(create_client_session(), loop=loop)

    icm._loop.run_until_complete(fut_client_session)

    client_session = fut_client_session.result()

    fut = asyncio.ensure_future(
        icm._get_ephemeral(
            client_session,
            icm._credentials,
            icm._project,
            icm._instance,
            icm._pub_key.decode("UTF-8"),  # noqa
        ),
        loop=loop,
    )

    icm._loop.run_until_complete(fut)
    icm._loop.close()

    result = fut.result().split("\n")

    client_session.close()

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
    icm = InstanceConnectionManager(connect_string, loop)

    async def create_client_session():
        return aiohttp.ClientSession()

    fut_client_session = asyncio.ensure_future(create_client_session(), loop=loop)

    icm._loop.run_until_complete(fut_client_session)

    client_session = fut_client_session.result()

    fut = asyncio.ensure_future(
        icm._get_metadata(
            client_session, icm._credentials, icm._project, icm._instance
        ),
        loop=loop,
    )

    icm._loop.run_until_complete(fut)
    icm._loop.close()

    result = fut.result()

    client_session.close()

    assert result["ip_addresses"] is not None and isinstance(
        result["server_ca_cert"], str
    )
