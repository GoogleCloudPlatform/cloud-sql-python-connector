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

import platform
import socket
import ssl
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from google.cloud.sql.connector.exceptions import PlatformNotSupportedError
from google.cloud.sql.connector.pytds import connect


def stub_platform_linux() -> str:
    """Helper function to stub platform operating system as Linux."""
    return "Linux"


def stub_platform_windows() -> str:
    """Helper function to stub platform operating system as Windows."""
    return "Windows"


@pytest.mark.usefixtures("proxy_server")
async def test_pytds(context: ssl.SSLContext, kwargs: Any) -> None:
    """Test to verify that pytds gets to proper connection call."""
    ip_addr = "127.0.0.1"
    sock = context.wrap_socket(
        socket.create_connection((ip_addr, 3307)),
        server_hostname=ip_addr,
    )

    with patch("pytds.connect") as mock_connect:
        mock_connect.return_value = True
        connection = connect(ip_addr, sock, **kwargs)
        # verify that driver connection call would be made
        assert connection is True
        assert mock_connect.assert_called_once


@pytest.mark.usefixtures("proxy_server")
async def test_pytds_platform_error(context: ssl.SSLContext, kwargs: Any) -> None:
    """Test to verify that pytds.connect throws proper PlatformNotSupportedError."""
    ip_addr = "127.0.0.1"
    # stub operating system to Linux
    platform.system = stub_platform_linux
    assert platform.system() == "Linux"
    sock = context.wrap_socket(
        socket.create_connection((ip_addr, 3307)),
        server_hostname=ip_addr,
    )
    # add active_directory_auth to kwargs
    kwargs["active_directory_auth"] = True
    # verify that error is thrown with Linux and active_directory_auth
    with pytest.raises(PlatformNotSupportedError):
        connect(ip_addr, sock, **kwargs)


@pytest.mark.usefixtures("proxy_server")
async def test_pytds_windows_active_directory_auth(
    context: ssl.SSLContext, kwargs: Any
) -> None:
    """
    Test to verify that pytds gets to connection call on Windows with
    active_directory_auth arg set.
    """
    ip_addr = "127.0.0.1"
    # stub operating system to Windows
    platform.system = stub_platform_windows
    assert platform.system() == "Windows"
    sock = context.wrap_socket(
        socket.create_connection((ip_addr, 3307)),
        server_hostname=ip_addr,
    )
    # add active_directory_auth and server_name to kwargs
    kwargs["active_directory_auth"] = True
    kwargs["server_name"] = "test-server"
    with patch("pytds.connect") as mock_connect:
        mock_connect.return_value = True
        with patch("pytds.login.SspiAuth") as mock_login:
            mock_login.return_value = True
            connection = connect(ip_addr, sock, **kwargs)
        # verify that driver connection call would be made
        assert mock_login.assert_called_once
        assert connection is True
        assert mock_connect.assert_called_once



def test_pytds_import_error(kwargs: Any) -> None:
    """Test to verify that connect raises ImportError if pytds is not installed."""
    with patch.dict("sys.modules", {"pytds": None}):
        with pytest.raises(ImportError) as excinfo:
            connect("0.0.0.0", None, **kwargs)
        assert 'Unable to import module "pytds."' in str(excinfo.value)


def test_pytds_database_param(kwargs: Any) -> None:
    """Test that pytds wrapper accepts both 'db' and 'database'."""
    ip_addr = "127.0.0.1"
    sock = MagicMock(spec=ssl.SSLSocket)

    # Test with 'db'
    kwargs_db = kwargs.copy()
    kwargs_db["db"] = "my-db-1"
    with patch("pytds.connect") as mock_connect:
        connect(ip_addr, sock, **kwargs_db)
        mock_connect.assert_called_once_with(
            ip_addr,
            database="my-db-1",
            user=kwargs["user"],
            password=kwargs["password"],
            sock=sock,
        )

    # Test with 'database'
    kwargs_database = kwargs.copy()
    kwargs_database["database"] = "my-db-2"
    if "db" in kwargs_database:
        del kwargs_database["db"]
    with patch("pytds.connect") as mock_connect:
        connect(ip_addr, sock, **kwargs_database)
        mock_connect.assert_called_once_with(
            ip_addr,
            database="my-db-2",
            user=kwargs["user"],
            password=kwargs["password"],
            sock=sock,
        )


