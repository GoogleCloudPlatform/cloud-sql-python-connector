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

import asyncio
import socket
import ssl
from typing import Any

from mock import Mock
import pytest

from google.cloud.sql.connector import proxy

LOCAL_PROXY_MAX_MESSAGE_SIZE = 10485760

@pytest.mark.usefixtures("proxy_server")
@pytest.mark.asyncio
async def test_proxy_creates_folder(context: ssl.SSLContext, kwargs: Any) -> None:
    """Test to verify that the proxy server is getting back the task."""
    ip_addr = "127.0.0.1"
    path = "/tmp/connector-socket/socket"
    sock = context.wrap_socket(
        socket.create_connection((ip_addr, 3307)),
        server_hostname=ip_addr,
    )
    loop = asyncio.get_running_loop()

    task = proxy.start_local_proxy(sock, path, loop)
    assert (task is not None)
    
    proxy_task = asyncio.gather(task)
    try:
        await asyncio.wait_for(proxy_task, timeout=0.1)
    except (asyncio.CancelledError, asyncio.TimeoutError, TimeoutError):
        pass # This task runs forever so it is expected to throw this exception

@pytest.mark.usefixtures("proxy_server")
@pytest.mark.asyncio
async def test_local_proxy_communication(context: ssl.SSLContext, kwargs: Any) -> None:
    """Test to verify that the communication is getting through."""
    socket_path = "/tmp/connector-socket/socket"
    ssl_sock = Mock(spec=ssl.SSLSocket)
    loop = asyncio.get_running_loop()

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        ssl_sock.recv.return_value = b"Received"

        task = proxy.start_local_proxy(ssl_sock, socket_path, loop)
        
        client.connect(socket_path)
        client.sendall(b"Test")
        await asyncio.sleep(1)
        
        ssl_sock.sendall.assert_called_with(b"Test")
        response = client.recv(LOCAL_PROXY_MAX_MESSAGE_SIZE)
        assert (response == b"Received")

        client.close()
        await asyncio.sleep(1)

        proxy_task = asyncio.gather(task)
        await asyncio.wait_for(proxy_task, timeout=2)
