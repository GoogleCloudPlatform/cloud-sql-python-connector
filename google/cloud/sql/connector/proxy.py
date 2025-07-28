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
import os
from pathlib import Path
import socket
import ssl

from google.cloud.sql.connector.exceptions import LocalProxyStartupError

SERVER_PROXY_PORT = 3307
LOCAL_PROXY_MAX_MESSAGE_SIZE = 10485760

def start_local_proxy(
    ssl_sock: ssl.SSLSocket,
    socket_path: str,
    loop: asyncio.AbstractEventLoop
) -> asyncio.Task:
    """Helper function to start a UNIX based local proxy for
    transport messages through the SSL Socket.

    Args:
        ssl_sock (ssl.SSLSocket): An SSLSocket object created from the Cloud SQL
            server CA cert and ephemeral cert.
        socket_path: A system path that is going to be used to store the socket.
        loop (asyncio.AbstractEventLoop): Event loop to run asyncio tasks.

    Returns:
        asyncio.Task: The asyncio task containing the proxy server process.

    Raises:
        LocalProxyStartupError: Local UNIX socket based proxy was not able to
        get started.
    """
    unix_socket = None

    try:
        path_parts = socket_path.rsplit('/', 1)
        parent_directory = '/'.join(path_parts[:-1])

        desired_path = Path(parent_directory)
        desired_path.mkdir(parents=True, exist_ok=True)

        if os.path.exists(socket_path):
            os.remove(socket_path)
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        unix_socket.bind(socket_path)
        unix_socket.listen(1)
        unix_socket.setblocking(False)
        os.chmod(socket_path, 0o600)
    except Exception:
        raise LocalProxyStartupError(
            'Local UNIX socket based proxy was not able to get started.'
        )

    return loop.create_task(local_communication(unix_socket, ssl_sock, socket_path, loop))


async def local_communication(
  unix_socket, ssl_sock, socket_path, loop
):
    try:
        client, _ = await loop.sock_accept(unix_socket)

        while True:
            data = await loop.sock_recv(client, LOCAL_PROXY_MAX_MESSAGE_SIZE)
            if not data:
              client.close()
              break
            ssl_sock.sendall(data)
            response = ssl_sock.recv(LOCAL_PROXY_MAX_MESSAGE_SIZE)
            await loop.sock_sendall(client, response)
    except Exception:
        pass
    finally:
        client.close()
        os.remove(socket_path) # Clean up the socket file
