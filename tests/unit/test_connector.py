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
import asyncio

from google.cloud.sql.connector import Connector, IPTypes
from google.cloud.sql.connector import connector as global_connector
from google.cloud.sql.connector.connector import _default_connector

from mock import patch
from typing import Any

# import mocks
from mocks import MockInstance


async def timeout_stub(*args: Any, **kwargs: Any) -> None:
    """Timeout stub for Instance.connect()"""
    # sleep 10 seconds
    await asyncio.sleep(10)


def test_connect_timeout() -> None:
    """Test that connection times out after custom timeout."""
    connect_string = "test-project:test-region:test-instance"

    instance = MockInstance()
    mock_instances = {}
    mock_instances[connect_string] = instance
    # stub instance to raise timeout
    setattr(instance, "connect_info", timeout_stub)
    # init connector
    connector = Connector()
    # attempt to connect with timeout set to 5s
    with patch.dict(connector._instances, mock_instances):
        pytest.raises(
            TimeoutError,
            connector.connect,
            connect_string,
            "pymysql",
            timeout=5,
        )


def test_connect_enable_iam_auth_error() -> None:
    """Test that calling connect() with different enable_iam_auth
    argument values throws error."""
    connect_string = "my-project:my-region:my-instance"
    # create mock instance with enable_iam_auth=False
    instance = MockInstance(enable_iam_auth=False)
    mock_instances = {}
    mock_instances[connect_string] = instance
    # init Connector
    connector = Connector()
    with patch.dict(connector._instances, mock_instances):
        # try to connect using enable_iam_auth=True, should raise error
        pytest.raises(
            ValueError,
            connector.connect,
            connect_string,
            "pg8000",
            enable_iam_auth=True,
        )
    # remove mock_instance to avoid destructor warnings
    connector._instances = {}


def test_Connector_Init() -> None:
    """Test that Connector __init__ sets default properties properly."""
    connector = Connector()
    assert connector._ip_type == IPTypes.PUBLIC
    assert connector._enable_iam_auth is False
    assert connector._timeout == 30
    assert connector._credentials is None
    connector.close()


def test_Connector_connect(connector: Connector) -> None:
    """Test that Connector.connect can properly return a DB API connection."""
    connect_string = "my-project:my-region:my-instance"
    # patch db connection creation
    with patch("pg8000.dbapi.connect") as mock_connect:
        mock_connect.return_value = True
        connection = connector.connect(
            connect_string, "pg8000", user="my-user", password="my-pass", db="my-db"
        )
        # verify connector made connection call
        assert connection is True


def test_global_connect(connector: Connector) -> None:
    """Test that global connect properly make connection call to default connector."""
    connect_string = "my-project:my-region:my-instance"
    # verify default_connector is not set
    assert _default_connector is None
    # set global connector
    global_connector._default_connector = connector
    # patch db connection creation
    with patch("pg8000.dbapi.connect") as mock_connect:
        mock_connect.return_value = True
        # connect using global connector
        connection = global_connector.connect(
            connect_string, "pg8000", user="my-user", password="my-pass", db="my-db"
        )

    # verify default_connector is now set
    from google.cloud.sql.connector.connector import (
        _default_connector as default_connector,
    )

    assert isinstance(default_connector, Connector)

    # verify attributes of default connector
    assert default_connector._ip_type == IPTypes.PUBLIC
    assert default_connector._enable_iam_auth is False
    assert default_connector._timeout == 30
    assert default_connector._credentials is None

    # verify global connector made connection call
    assert connection is True
