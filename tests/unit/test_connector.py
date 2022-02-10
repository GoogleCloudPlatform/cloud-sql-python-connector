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

import pytest  # noqa F401 Needed to run the tests
from google.cloud.sql.connector.instance_connection_manager import (
    IPTypes,
    InstanceConnectionManager,
)
from google.cloud.sql.connector import connector
from google.cloud.sql.connector.utils import generate_keys
from google.auth.credentials import Credentials
import asyncio
from unittest.mock import patch
from typing import Any


def test_connect_timeout(
    fake_credentials: Credentials, async_loop: asyncio.AbstractEventLoop
) -> None:
    timeout = 10
    connect_string = "test-project:test-region:test-instance"

    async def timeout_stub(*args: Any, **kwargs: Any) -> None:
        try:
            await asyncio.sleep(timeout + 10)
        except asyncio.CancelledError:
            return None

    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)
    setattr(icm, "_connect", timeout_stub)

    mock_instances = {}
    mock_instances[connect_string] = icm
    mock_connector = connector.Connector()
    connector._default_connector = mock_connector
    with patch.dict(mock_connector._instances, mock_instances):
        pytest.raises(
            TimeoutError,
            connector.connect,
            connect_string,
            "pymysql",
            timeout=timeout,
        )


def test_connect_enable_iam_auth_error(
    fake_credentials: Credentials, async_loop: asyncio.AbstractEventLoop
) -> None:
    """Test that giving different enable_iam_auth argument values throws error."""
    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        # set InstanceConnectionManager's enable_iam_auth=False
        icm = InstanceConnectionManager(
            connect_string, "pymysql", keys, async_loop, enable_iam_auth=False
        )
        mock_instances = {}
        mock_instances[connect_string] = icm
        mock_connector = connector.Connector()
        connector._default_connector = mock_connector
        # try to connect using enable_iam_auth=True
        with patch.dict(mock_connector._instances, mock_instances):
            pytest.raises(
                ValueError,
                connector.connect,
                connect_string,
                "pymysql",
                enable_iam_auth=True,
            )


def test_default_Connector_Init() -> None:
    """Test that default Connector __init__ sets properties properly."""
    default_connector = connector.Connector()
    assert default_connector._ip_type == IPTypes.PUBLIC
    assert default_connector._enable_iam_auth is False
    assert default_connector._timeout == 30
    assert default_connector._credentials is None
