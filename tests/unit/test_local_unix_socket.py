"""
Copyright 2025 Google LLC

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
from mock import PropertyMock
import pytest

from google.cloud.sql.connector.local_unix_socket import connect


@pytest.mark.usefixtures("proxy_server")
async def test_local_unix_socket(context: ssl.SSLContext, kwargs: Any) -> None:
    """Test to verify that local_unix_socket gets to proper connection call."""
    ip_addr = "127.0.0.1"
    sock = context.wrap_socket(
        socket.create_connection((ip_addr, 3307)),
        server_hostname=ip_addr,
    )
    connection = connect(ip_addr, sock, **kwargs)
    assert connection == sock
