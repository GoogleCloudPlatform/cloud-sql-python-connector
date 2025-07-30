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

from mock import patch
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
