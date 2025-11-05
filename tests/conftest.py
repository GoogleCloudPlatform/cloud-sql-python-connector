"""
Copyright 2021 Google LLC

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
from asyncio import Server
import logging
import os
import socket
import ssl
from threading import Thread
from typing import Any, AsyncGenerator

from aiofiles.tempfile import TemporaryDirectory
from aiohttp import web
from cryptography.hazmat.primitives import serialization
import pytest  # noqa F401 Needed to run the tests
from unit.mocks import create_ssl_context  # type: ignore
from unit.mocks import FakeCredentials  # type: ignore
from unit.mocks import FakeCSQLInstance  # type: ignore

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.instance import RefreshAheadCache
from google.cloud.sql.connector.utils import generate_keys
from google.cloud.sql.connector.utils import write_to_file

SCOPES = ["https://www.googleapis.com/auth/sqlservice.admin"]
logger = logging.getLogger(name=__name__)


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--run_private_ip",
        action="store_true",
        default=False,
        help="run tests that need to be running in VPC network",
    )


def pytest_configure(config: Any) -> None:
    config.addinivalue_line(
        "markers", "private_ip: mark test as requiring private IP access"
    )


def pytest_collection_modifyitems(config: Any, items: Any) -> None:
    if config.getoption("--run_private_ip"):
        return
    skip_private_ip = pytest.mark.skip(reason="need --run_private_ip option to run")
    for item in items:
        if "private_ip" in item.keywords:
            item.add_marker(skip_private_ip)


@pytest.fixture
def connect_string() -> str:
    """
    Retrieves a valid connection string from the environment and
    returns it.
    """
    try:
        connect_string = os.environ["MYSQL_CONNECTION_NAME"]
    except KeyError:
        raise KeyError(
            "Please set environment variable 'INSTANCE_CONNECTION"
            + "_NAME' to a valid Cloud SQL connection string."
        )

    return connect_string


@pytest.fixture
def fake_credentials() -> FakeCredentials:
    return FakeCredentials()


async def start_proxy_server_async(
    instance: FakeCSQLInstance, with_read_write: bool
) -> Server:
    """Run local proxy server capable of performing mTLS"""
    ip_address = "127.0.0.1"
    port = 3307
    logger.debug("start_proxy_server_async started")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    # tmpdir and its contents are automatically deleted after the CA cert
    # and cert chain are loaded into the SSLcontext. The values
    # need to be written to files in order to be loaded by the SSLContext
    server_key_bytes = instance.server_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    async with TemporaryDirectory() as tmpdir:
        server_filename, _, key_filename = await write_to_file(
            tmpdir, instance.server_cert_pem, "", server_key_bytes
        )
        context.load_cert_chain(server_filename, key_filename)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        logger.debug("Received fake connection")
        if with_read_write:
            line = await reader.readline()
            logger.debug(f"Received request {line}")
            writer.write("world\n".encode("utf-8"))
            await writer.drain()
            logger.debug("Wrote response")
            if writer.can_write_eof():
                writer.write_eof()
        logger.debug("Closing connection")
        writer.close()
        await writer.wait_closed()
        logger.debug("Closed connection")

    server = await asyncio.start_server(
        handler, host=ip_address, port=port, ssl=context
    )
    logger.debug("Listening on 127.0.0.1:3307")
    asyncio.create_task(server.serve_forever())
    return server


@pytest.fixture(scope="function")
def proxy_server_async(fake_instance: FakeCSQLInstance):
    # Create an event loop in a different thread for the server
    loop = asyncio.new_event_loop()

    def f(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
        logger.debug("exiting thread")

    t = Thread(target=f, args=(loop,))
    t.start()
    t.join(1)

    # Submit the server task to the thread
    server_fut = asyncio.run_coroutine_threadsafe(
        start_proxy_server_async(fake_instance, True), loop
    )
    while not server_fut.done():
        t.join(0.1)
    logger.debug("proxy_server_async server started")
    yield
    logger.debug("proxy_server_async fixture done")

    logger.debug("proxy_server_async fixture cleanup")

    # Stop the server after the test is complete
    async def stop_server():
        logger.debug("inside_cleanup closing server")
        server_fut.result().close()
        loop.shutdown_asyncgens()
        loop.stop()
        logger.debug("inside_cleanup end")

    logger.debug("cleanup starting")
    asyncio.run_coroutine_threadsafe(stop_server(), loop)
    logger.debug("cleanup done")
    while loop.is_running():
        t.join(0.1)
    logger.debug("loop is not running")
    loop.close()
    t.join(1)


@pytest.fixture(scope="function")
def proxy_server(fake_instance: FakeCSQLInstance):
    # Create an event loop in a different thread for the server
    loop = asyncio.new_event_loop()

    def f(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
        logger.debug("exiting thread")

    t = Thread(target=f, args=(loop,))
    t.start()

    # Submit the server task to the thread
    server_fut = asyncio.run_coroutine_threadsafe(
        start_proxy_server_async(fake_instance, False), loop
    )
    while not server_fut.done():
        t.join(0.1)
    logger.debug("proxy_server_async server started")
    yield
    logger.debug("proxy_server_async fixture done")

    logger.debug("proxy_server_async fixture cleanup")

    # Stop the server after the test is complete
    async def stop_server():
        logger.debug("inside_cleanup closing server")
        server_fut.result().close()
        loop.shutdown_asyncgens()
        loop.stop()
        logger.debug("inside_cleanup end")

    logger.debug("cleanup starting")
    asyncio.run_coroutine_threadsafe(stop_server(), loop)
    logger.debug("cleanup done")
    while loop.is_running():
        t.join(0.1)
    logger.debug("loop is not running")
    loop.close()


@pytest.fixture
async def context(fake_instance: FakeCSQLInstance) -> ssl.SSLContext:
    return await create_ssl_context(fake_instance)


@pytest.fixture
def kwargs() -> Any:
    """Database connection keyword arguments."""
    kwargs = {"user": "test-user", "db": "test-db", "password": "test-password"}
    return kwargs


@pytest.fixture(scope="session")
def fake_instance() -> FakeCSQLInstance:
    return FakeCSQLInstance()


@pytest.fixture
async def fake_client(
    fake_credentials: FakeCredentials,
    fake_instance: FakeCSQLInstance,
    aiohttp_client: Any,
) -> CloudSQLClient:
    app = web.Application()
    # add SQL Server instance for additional tests
    # TODO: remove when SQL Server supports IAM authN
    sqlserver_instance = FakeCSQLInstance(
        name="sqlserver-instance", db_version="SQLSERVER_2019_STANDARD"
    )
    metadata_uri = f"/sql/v1beta4/projects/{fake_instance.project}/instances/{fake_instance.name}/connectSettings"
    app.router.add_get(metadata_uri, fake_instance.connect_settings)
    sqlserver_metadata_uri = f"/sql/v1beta4/projects/{sqlserver_instance.project}/instances/{sqlserver_instance.name}/connectSettings"
    app.router.add_get(sqlserver_metadata_uri, sqlserver_instance.connect_settings)
    client_cert_uri = f"/sql/v1beta4/projects/{fake_instance.project}/instances/{fake_instance.name}:generateEphemeralCert"
    app.router.add_post(client_cert_uri, fake_instance.generate_ephemeral)
    sqlserver_client_cert_uri = f"/sql/v1beta4/projects/{sqlserver_instance.project}/instances/{sqlserver_instance.name}:generateEphemeralCert"
    app.router.add_post(
        sqlserver_client_cert_uri, sqlserver_instance.generate_ephemeral
    )
    client_session = await aiohttp_client(app)
    client = CloudSQLClient("", "", fake_credentials, client=client_session)
    # add instance to client to control cert expiration etc.
    client.instance = fake_instance
    return client


@pytest.fixture
async def cache(fake_client: CloudSQLClient) -> AsyncGenerator[RefreshAheadCache, None]:
    keys = asyncio.create_task(generate_keys())
    cache = RefreshAheadCache(
        ConnectionName("test-project", "test-region", "test-instance"),
        client=fake_client,
        keys=keys,
    )
    yield cache
    await cache.close()


@pytest.fixture
def connected_socket_pair() -> tuple[socket.socket, socket.socket]:
    """A fixture that provides a pair of connected sockets."""
    server, client = socket.socketpair()
    yield server, client
    server.close()
    client.close()


@pytest.fixture
async def echo_server() -> AsyncGenerator[tuple[str, int], None]:
    """A fixture that starts an asyncio echo server."""

    async def handle_echo(reader, writer):
        while True:
            data = await reader.read(100)
            if not data:
                break
            writer.write(data)
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_echo, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    yield addr
    server.close()
    await server.wait_closed()