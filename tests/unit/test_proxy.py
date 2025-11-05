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
import shutil
import tempfile
from unittest.mock import MagicMock

import pytest

from google.cloud.sql.connector.proxy import Proxy, ServerConnectionFactory


@pytest.fixture
def short_tmpdir():
    """Create a temporary directory with a short path."""
    dir_path = tempfile.mkdtemp(dir="/tmp")
    yield dir_path
    shutil.rmtree(dir_path)


@pytest.mark.asyncio
async def test_proxy_creates_folder_and_socket(short_tmpdir):
    """
    Test to verify that the Proxy server creates the folder and socket file.
    """
    socket_path = os.path.join(short_tmpdir, ".s.PGSQL.5432")
    connector = MagicMock(spec=ServerConnectionFactory)
    proxy = Proxy(socket_path, connector, asyncio.get_event_loop())
    await proxy.start()

    assert os.path.exists(short_tmpdir)
    assert os.path.exists(socket_path)

    await proxy.close()


# A mock ServerConnectionFactory for testing purposes.
class MockServerConnectionFactory(ServerConnectionFactory):
    def __init__(self, loop):
        self.server_protocol = None
        self.server_transport = None
        self.connect_called = asyncio.Event()
        self.connect_ran = asyncio.Event()
        self.force_connect_error = False
        self.loop = loop
        self.server_data = bytearray()

    async def connect(self, protocol_fn):
        self.connect_called.set()
        if self.force_connect_error:
            raise Exception("Forced connection error")

        self.server_protocol = protocol_fn()
        # Create a mock transport for server-side communication
        self.server_transport = MagicMock(spec=asyncio.Transport)
        self.server_transport.write.side_effect = self.server_data.extend
        self.server_transport.is_closing.return_value = False

        # Simulate connection made for the server protocol
        self.server_protocol.connection_made(self.server_transport)
        self.connect_ran.set()
        return self.server_transport, self.server_protocol


# Test fixture for the proxy
@pytest.fixture
async def proxy_server(short_tmpdir):
    socket_path = os.path.join(short_tmpdir, ".s.PGSQL.5432")
    loop = asyncio.get_event_loop()
    connector = MockServerConnectionFactory(loop)
    proxy = Proxy(socket_path, connector, loop)
    await proxy.start()
    yield proxy, socket_path, connector
    await proxy.close()


@pytest.mark.asyncio
async def test_proxy_client_to_server(proxy_server):
    """
    1. Create a new proxy. Open a client socket to the proxy. Write data to
    the client socket. Read data from the server. Check that the data was
    received by the server.
    """
    proxy, socket_path, connector = proxy_server
    reader, writer = await asyncio.open_unix_connection(socket_path)

    # wait for server connection to be established
    await connector.connect_called.wait()

    # Write data to the client socket
    test_data = b"test data from client"
    writer.write(test_data)
    await writer.drain()

    # Check that the data was received by the server
    await asyncio.sleep(0.01)  # give event loop a chance to run
    assert connector.server_data == test_data

    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_proxy_server_to_client(proxy_server):
    """
    2. Create a new proxy, Open a client socket. Write data to the server
    socket. Read data from the client socket. Check that the data was
    received by the client.
    """
    proxy, socket_path, connector = proxy_server
    reader, writer = await asyncio.open_unix_connection(socket_path)

    # wait for server connection to be established
    await connector.connect_called.wait()

    # Write data from the server to the client
    test_data = b"test data from server"
    connector.server_protocol.data_received(test_data)

    # Read data from the client socket
    received_data = await reader.read(len(test_data))

    # Check that the data was received by the client
    assert received_data == test_data

    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_proxy_server_connect_fails(proxy_server):
    """
    3. Create a new proxy. Open a client socket. The server socket fails to
    connect. Check that the client socket is closed.
    """
    proxy, socket_path, connector = proxy_server
    connector.force_connect_error = True

    reader, writer = await asyncio.open_unix_connection(socket_path)

    # wait for server connection to be attempted
    await connector.connect_called.wait()

    assert os.path.exists(socket_path) == True

    # The client connection should be closed by the proxy
    # Reading should return EOF
    data = await reader.read(100)
    assert data == b""

    await asyncio.sleep(1)  # give proxy a chance to shut down

    assert os.path.exists(socket_path) == False


@pytest.mark.asyncio
async def test_proxy_client_closes_connection(proxy_server):
    """
    4. Create a new proxy. Open a client socket. Check that the server
    socket connected. Close the client socket. Check that the server socket
    is closed gracefully.
    """
    proxy, socket_path, connector = proxy_server
    reader, writer = await asyncio.open_unix_connection(socket_path)

    # wait for server connection to be established
    await connector.connect_called.wait()
    assert connector.server_transport is not None

    # Close the client socket
    writer.close()
    await writer.wait_closed()

    # Check that the server socket is closed
    await asyncio.sleep(0.01)  # give event loop a chance to run
    connector.server_transport.close.assert_called_once()


#
# TCP Server Fixtures and Tests
#


@pytest.fixture
async def tcp_echo_server():
    """Fixture to create a TCP echo server."""

    async def echo(reader, writer):
        try:
            while not reader.at_eof():
                data = await reader.read(1024)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    host, port = addr[0], addr[1]

    yield host, port

    server.close()
    await server.wait_closed()


@pytest.fixture
async def tcp_server_accept_and_close():
    """Fixture to create a TCP server that accepts and immediately closes."""

    async def accept_and_close(reader, writer):
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept_and_close, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    host, port = addr[0], addr[1]

    yield host, port

    server.close()
    await server.wait_closed()


class TCPServerConnectionFactory(ServerConnectionFactory):
    """A ServerConnectionFactory that connects to a TCP server."""

    def __init__(self, host, port, loop):
        self.host = host
        self.port = port
        self.loop = loop
        self.connect_called = asyncio.Event()
        self.connect_ran = asyncio.Event()
        self.server_transport: asyncio.Transport | None = None
        self.server_protocol: asyncio.Protocol | None = None

    async def connect(self, protocol_fn):
        self.connect_called.set()
        transport, protocol = await asyncio.wait_for(self.loop.create_connection(
            protocol_fn, self.host, self.port,
        ), timeout=0.5)
        self.server_transport = transport
        self.server_protocol = protocol
        self.connect_ran.set()
        return transport, protocol


@pytest.fixture
async def tcp_proxy_server(short_tmpdir, tcp_echo_server):
    """Fixture to set up a proxy with a TCP backend."""
    socket_path = os.path.join(short_tmpdir, ".s.PGSQL.5432")
    loop = asyncio.get_event_loop()
    host, port = tcp_echo_server
    connector = TCPServerConnectionFactory(host, port, loop)
    proxy = Proxy(socket_path, connector, loop)
    await proxy.start()
    yield proxy, socket_path, connector
    await proxy.close()


@pytest.fixture
async def tcp_proxy_server_with_closing_backend(short_tmpdir, tcp_server_accept_and_close):
    """Fixture to set up a proxy with a TCP backend that closes immediately."""
    socket_path = os.path.join(short_tmpdir, ".s.PGSQL.5432")
    loop = asyncio.get_event_loop()
    host, port = tcp_server_accept_and_close
    connector = TCPServerConnectionFactory(host, port, loop)
    proxy = Proxy(socket_path, connector, loop)
    await proxy.start()
    yield proxy, socket_path, connector
    await proxy.close()


@pytest.fixture
async def tcp_proxy_server_with_no_tcp_server(short_tmpdir):
    """Fixture to set up a proxy with a TCP backend that closes immediately."""
    socket_path = os.path.join(short_tmpdir, ".s.PGSQL.5432")
    loop = asyncio.get_event_loop()
    connector = TCPServerConnectionFactory("localhost", "34532", loop)
    proxy = Proxy(socket_path, connector, loop)
    await proxy.start()
    yield proxy, socket_path, connector
    await proxy.close()


@pytest.mark.asyncio
async def test_tcp_proxy_echo(tcp_proxy_server):
    """
    Tests data flow from client to a TCP server and back.
    """
    proxy, socket_path, connector = tcp_proxy_server
    reader, writer = await asyncio.open_unix_connection(socket_path)
    await connector.connect_called.wait()

    test_data = b"test data from client"
    writer.write(test_data)
    await writer.drain()

    # Read echoed data back from the server
    received_data = await reader.read(len(test_data))
    assert received_data == test_data

    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_tcp_proxy_server_connection_refused(tcp_proxy_server_with_no_tcp_server):
    """
    Tests that the client socket is closed when TCP connection fails.
    """
    proxy, socket_path, connector = tcp_proxy_server_with_no_tcp_server

    reader, writer = await asyncio.open_unix_connection(socket_path)
    await connector.connect_called.wait()
    test_data = b"test data from client"
    writer.write(test_data)
    await writer.drain()

    await asyncio.sleep(1.5)
    assert os.path.exists(socket_path) == False



@pytest.mark.asyncio
async def test_tcp_proxy_server_unexpected_closed(tcp_proxy_server_with_closing_backend):
    """
    Tests that the client socket is closed when TCP connection fails.
    """
    proxy, socket_path, connector = tcp_proxy_server_with_closing_backend

    reader, writer = await asyncio.open_unix_connection(socket_path)
    await connector.connect_called.wait()

    # The client connection should be closed by the proxy
    data = await reader.read(100)
    assert data == b""

    await asyncio.sleep(0.5)  # give event loop a chance to run
    assert os.path.exists(socket_path) == False



@pytest.mark.asyncio
async def test_tcp_proxy_client_closes_connection(tcp_proxy_server):
    """
    Tests that closing the client socket closes the TCP server socket.
    """
    proxy, socket_path, connector = tcp_proxy_server
    reader, writer = await asyncio.open_unix_connection(socket_path)
    await connector.connect_ran.wait()

    assert connector.server_transport is not None
    assert not connector.server_transport.is_closing()

    # Close the client socket
    writer.close()
    await writer.wait_closed()

    # Check that the server socket is closing
    await asyncio.sleep(0.01)
    assert connector.server_transport.is_closing()