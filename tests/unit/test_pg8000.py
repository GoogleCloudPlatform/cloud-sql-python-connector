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

from google.cloud.sql.connector.pg8000 import connect


@pytest.mark.usefixtures("proxy_server")
async def test_pg8000(context: ssl.SSLContext, kwargs: Any) -> None:
    """Test to verify that pg8000 gets to proper connection call."""
    ip_addr = "127.0.0.1"
    sock = context.wrap_socket(
        socket.create_connection((ip_addr, 3307)),
        server_hostname=ip_addr,
    )
    with patch("pg8000.dbapi.connect") as mock_connect:
        mock_connect.return_value = True
        connection = connect(ip_addr, sock, **kwargs)
        assert connection is True
        # verify that driver connection call would be made
        assert mock_connect.assert_called_once


def test_pg8000_import_error(kwargs: Any) -> None:
    """Test to verify that connect raises ImportError if pg8000 is not installed."""
    with patch.dict("sys.modules", {"pg8000": None}):
        with pytest.raises(ImportError) as excinfo:
            connect("0.0.0.0", None, **kwargs)
        assert 'Unable to import module "pg8000."' in str(excinfo.value)


def test_pg8000_database_param(kwargs: Any) -> None:
    """Test that pg8000 wrapper accepts both 'db' and 'database'."""
    ip_addr = "127.0.0.1"
    sock = MagicMock(spec=ssl.SSLSocket)

    # Test with 'db'
    kwargs_db = kwargs.copy()
    kwargs_db["db"] = "my-db-1"
    with patch("pg8000.dbapi.connect") as mock_connect:
        connect(ip_addr, sock, **kwargs_db)
        mock_connect.assert_called_once_with(
            kwargs["user"],
            database="my-db-1",
            password=kwargs.get("password"),
            sock=sock,
        )

    # Test with 'database'
    kwargs_database = kwargs.copy()
    kwargs_database["database"] = "my-db-2"
    if "db" in kwargs_database:
        del kwargs_database["db"]
    with patch("pg8000.dbapi.connect") as mock_connect:
        connect(ip_addr, sock, **kwargs_database)
        mock_connect.assert_called_once_with(
            kwargs["user"],
            database="my-db-2",
            password=kwargs.get("password"),
            sock=sock,
        )


def test_pg8000_database_missing(kwargs: Any) -> None:
    """Test that pg8000 wrapper raises KeyError if database is missing."""
    if "db" in kwargs:
        del kwargs["db"]
    if "database" in kwargs:
        del kwargs["database"]
    with pytest.raises(KeyError, match="database"):
        connect("0.0.0.0", None, **kwargs)


