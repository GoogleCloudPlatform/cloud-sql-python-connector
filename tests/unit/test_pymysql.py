"""
Copyright 2022 Google LLC

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

import socket
import ssl
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from google.cloud.sql.connector.pymysql import connect as pymysql_connect


class MockConnection:
    def __init__(self, host: str, defer_connect: bool, **kwargs: Any) -> None:
        pass

    def connect(sock: ssl.SSLSocket) -> None:  # type: ignore
        assert isinstance(sock, ssl.SSLSocket)


@pytest.mark.usefixtures("proxy_server")
@pytest.mark.asyncio
async def test_pymysql(context: ssl.SSLContext, kwargs: Any) -> None:
    """Test to verify that pymysql gets to proper connection call."""
    ip_addr = "127.0.0.1"
    sock = context.wrap_socket(
        socket.create_connection((ip_addr, 3307)),
        server_hostname=ip_addr,
    )
    kwargs["timeout"] = 30
    with patch("pymysql.Connection") as mock_connect:
        mock_connect.return_value = MockConnection
        pymysql_connect(ip_addr, sock, **kwargs)
        # verify that driver connection call would be made
        assert mock_connect.assert_called_once


def test_pymysql_import_error(kwargs: Any) -> None:
    """Test to verify that connect raises ImportError if pymysql is not installed."""
    kwargs["timeout"] = 30
    with patch.dict("sys.modules", {"pymysql": None}):
        with pytest.raises(ImportError) as excinfo:
            pymysql_connect("0.0.0.0", None, **kwargs)
        assert 'Unable to import module "pymysql."' in str(excinfo.value)


def test_pymysql_database_param(kwargs: Any) -> None:
    """Test that pymysql wrapper accepts both 'db' and 'database' and maps 'db' to 'database'."""
    ip_addr = "127.0.0.1"
    sock = MagicMock(spec=ssl.SSLSocket)
    kwargs["timeout"] = 30

    # Test with 'db'
    kwargs_db = kwargs.copy()
    kwargs_db["db"] = "my-db-1"
    with patch("pymysql.Connection") as mock_conn:
        pymysql_connect(ip_addr, sock, **kwargs_db)
        _, call_kwargs = mock_conn.call_args
        assert call_kwargs["database"] == "my-db-1"
        assert "db" not in call_kwargs

    # Test with 'database'
    kwargs_database = kwargs.copy()
    kwargs_database["database"] = "my-db-2"
    if "db" in kwargs_database:
        del kwargs_database["db"]
    with patch("pymysql.Connection") as mock_conn:
        pymysql_connect(ip_addr, sock, **kwargs_database)
        _, call_kwargs = mock_conn.call_args
        assert call_kwargs["database"] == "my-db-2"
        assert "db" not in call_kwargs


