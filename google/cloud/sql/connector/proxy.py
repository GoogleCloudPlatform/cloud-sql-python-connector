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

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
import asyncio
from functools import partial
import logging
import os
from pathlib import Path
from typing import Callable, List

logger = logging.getLogger(name=__name__)


class BaseProxyProtocol(asyncio.Protocol):
    """
    A protocol to proxy data between two transports.
    """

    def __init__(self, proxy: Proxy):
        super().__init__()
        self.proxy = proxy
        self._buffer = bytearray()
        self._target: asyncio.Transport | None = None
        self.transport: asyncio.Transport | None = None
        self._cached: List[bytes] = []
        logger.debug(f"__init__  {self}")

    def connection_made(self, transport):
        logger.debug(f"connection_made {self}")
        self.transport = transport

    def data_received(self, data):
        if self._target is None:
            self._cached.append(data)
        else:
            self._target.write(data)

    def set_target(self, target: asyncio.Transport):
        logger.debug(f"set_target {self}")
        self._target = target
        if self._cached:
            self._target.writelines(self._cached)
            self._cached = []

    def eof_received(self):
        logger.debug(f"eof_received {self}")
        if self._target is not None:
            self._target.write_eof()

    def connection_lost(self, exc: Exception | None):
        logger.debug(f"connection_lost {exc} {self}")
        if self._target is not None:
            self._target.close()


class ProxyClientConnection:
    """
    Holds all of the tasks and details for a client proxy
    """

    def __init__(
        self,
        client_transport: asyncio.Transport,
        client_protocol: ClientToServerProtocol,
    ):
        self.client_transport = client_transport
        self.client_protocol = client_protocol
        self.server_transport: asyncio.Transport | None = None
        self.server_protocol: ServerToClientProtocol | None = None
        self.task: asyncio.Task | None = None

    def close(self):
        if self.client_transport is not None:
            self._close_transport(self.client_transport)
        if self.server_transport is not None:
            self._close_transport(self.server_transport)

    def _close_transport(self, transport:asyncio.Transport):
        if transport.is_closing():
            return
        if transport.can_write_eof():
            transport.write_eof()
        else:
            transport.close()

class ClientToServerProtocol(BaseProxyProtocol):
    """
    Protocol to copy bytes from the unix socket client to the database server
    """

    def __init__(self, proxy: Proxy):
        super().__init__(proxy)
        self._buffer = bytearray()
        self._target: asyncio.Transport | None = None
        logger.debug(f"__init__ {self}")

    def connection_made(self, transport):
        # When a connection is made, open the server connection
        super().connection_made(transport)
        self.proxy._handle_client_connection(transport, self)


class ServerToClientProtocol(BaseProxyProtocol):
    """
    Protocol to copy bytes from the database server to the client socket
    """

    def __init__(self, proxy: Proxy, cconn: ProxyClientConnection):
        super().__init__(proxy)
        self._buffer = bytearray()
        self._target = cconn.client_transport
        self._client_protocol = cconn.client_protocol
        logger.debug(f"__init__ {self}")

    def connection_made(self, transport):
        super().connection_made(transport)
        self._client_protocol.set_target(transport)

class ServerConnectionFactory(ABC):
    """
    ServerConnectionFactory is an abstract class that provides connections to the service.
    """
    @abstractmethod
    async def connect(self, protocol_fn: Callable[[], asyncio.Protocol]):
        """
        Establishes a connection to the server and configures it to use the protocol
        returned from protocol_fn, with asyncio.EventLoop.create_connection().
        :param protocol_fn: the protocol function
        :return: None
        """
        pass

class Proxy:
    """
    A class to represent a local Unix socket proxy for a Cloud SQL instance.
    This class manages a Unix socket that listens for incoming connections and
    proxies them to a Cloud SQL instance.
    """

    def __init__(
        self,
        unix_socket_path: str,
        server_connection_factory: ServerConnectionFactory,
        loop: asyncio.AbstractEventLoop,
    ):
        """
        Creates a new Proxy
        :param unix_socket_path: the path to listen for the proxy connection
        :param loop: The event loop
        :param instance_connect: A function that will establish the async connection to the server

        The instance_connect function is an asynchronous function that should set up a new connection.
        It takes one argument - another function that
        """
        self.unix_socket_path = unix_socket_path
        self._loop = loop
        self._server: asyncio.AbstractServer | None = None
        self._client_connections: set[ProxyClientConnection] = set()
        self._server_connection_factory = server_connection_factory

    async def start(self) -> None:
        """Starts the Unix socket server."""
        if os.path.exists(self.unix_socket_path):
            os.remove(self.unix_socket_path)

        parent_dir = Path(self.unix_socket_path).parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        def new_protocol() -> ClientToServerProtocol:
            return ClientToServerProtocol(self)

        self._server = await self._loop.create_unix_server(
            new_protocol, path=self.unix_socket_path
        )
        self._loop.create_task(self._server.serve_forever())

    def _handle_client_connection(
        self,
        client_transport: asyncio.Transport,
        client_protocol: ClientToServerProtocol,
    ) -> None:
        """
        Register a new client connection and initiate the task to create a database connection.
        This is called by ClientToServerProtocol.connection_made

        :param client_transport: the client transport for the client unix socket
        :param client_protocol:  the instance for the
        :return: None
        """
        conn = ProxyClientConnection(client_transport, client_protocol)
        self._client_connections.add(conn)
        conn.task = self._loop.create_task(self._create_db_instance_connection(conn))
        conn.task.add_done_callback(lambda _: self._client_connections.discard(conn))

    async def _create_db_instance_connection(self, conn: ProxyClientConnection) -> None:
        """
        Manages a single proxy connection from a client to the Cloud SQL instance.
        """
        try:
            logger.debug("_proxy_connection() started")
            new_protocol = partial(ServerToClientProtocol, self, conn)

            # Establish connection to the database
            await self._server_connection_factory.connect(new_protocol)
            logger.debug("_proxy_connection() succeeded")

        except Exception as e:
            logger.error(f"Error handling proxy connection: {e}")
            conn.close()
            raise e

    async def close(self) -> None:
        """
        Shuts down the proxy server and cleans up resources.
        """
        logger.info(f"Closing Unix socket proxy at {self.unix_socket_path}")

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        if self._client_connections:
            for conn in list(self._client_connections):
                conn.close()
            await asyncio.gather(
                *[c.task for c in self._client_connections if c.task is not None],
                return_exceptions=True,
            )

        if os.path.exists(self.unix_socket_path):
            os.remove(self.unix_socket_path)

        logger.info(f"Unix socket proxy for {self.unix_socket_path} closed.")
