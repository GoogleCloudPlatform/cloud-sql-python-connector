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
import selectors
import ssl

from google.cloud.sql.connector.exceptions import LocalProxyStartupError

LOCAL_PROXY_MAX_MESSAGE_SIZE = 10485760


class Proxy:
    """Creates an "accept loop" async task which will open the unix server socket and listen for new connections."""

    def __init__(
        self,
        connector,
        instance_connection_string: str,
        socket_path: str,
        loop: asyncio.AbstractEventLoop,
        **kwargs
    ) -> None:
        """Keeps track of all the async tasks and starts the accept loop for new connections.
        
        Args:
            connector (Connector): The instance where this Proxy class was created.

            instance_connection_string (str): The instance connection name of the
                Cloud SQL instance to connect to. Takes the form of
                "project-id:region:instance-name"

                Example: "my-project:us-central1:my-instance"

            socket_path (str): A system path that is going to be used to store the socket.

            loop (asyncio.AbstractEventLoop): Event loop to run asyncio tasks.

            **kwargs: Any driver-specific arguments to pass to the underlying
                driver .connect call.
        """
        self._connection_tasks = []
        self._addr = instance_connection_string
        self._kwargs = kwargs
        self._connector = connector

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

            self._task = loop.create_task(self.accept_loop(unix_socket, socket_path, loop))

        except Exception:
            raise LocalProxyStartupError(
                'Local UNIX socket based proxy was not able to get started.'
            )

    async def accept_loop(
        self,
        unix_socket,
        socket_path: str,
        loop: asyncio.AbstractEventLoop
    ) -> asyncio.Task:
        """Starts a UNIX based local proxy for transporting messages through
        the SSL Socket, and waits until there is a new connection to accept, to register it
        and keep track of it.
        
        Args:
            socket_path: A system path that is going to be used to store the socket.

            loop (asyncio.AbstractEventLoop): Event loop to run asyncio tasks.

        Raises:
            LocalProxyStartupError: Local UNIX socket based proxy was not able to
            get started.
        """
        print("on accept loop")
        while True:
            client, _ = await loop.sock_accept(unix_socket)
            self._connection_tasks.append(loop.create_task(self.client_socket(client, unix_socket, socket_path, loop))) 

    async def close_async(self):
        proxy_task = asyncio.gather(self._task)
        try:
            await asyncio.wait_for(proxy_task, timeout=0.1)
        except (asyncio.CancelledError, asyncio.TimeoutError, TimeoutError):
            pass # This task runs forever so it is expected to throw this exception


    async def client_socket(
        self, client, unix_socket, socket_path, loop
    ):
        try:
            ssl_sock = self._connector.connect(
                self._addr,
                'local_unix_socket',
                **self._kwargs
            )
            while True:
                data = await loop.sock_recv(client, LOCAL_PROXY_MAX_MESSAGE_SIZE)
                if not data:
                    client.close()
                    break
                ssl_sock.sendall(data)
                response = ssl_sock.recv(LOCAL_PROXY_MAX_MESSAGE_SIZE)
                await loop.sock_sendall(client, response)
        finally:
            client.close()
            os.remove(socket_path) # Clean up the socket file
