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

from mock import patch
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
    setattr(platform, "system", stub_platform_linux)
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
    setattr(platform, "system", stub_platform_windows)
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
