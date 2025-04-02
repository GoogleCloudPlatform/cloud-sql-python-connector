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


async def start_proxy_server(instance: FakeCSQLInstance) -> None:
    """Run local proxy server capable of performing mTLS"""
    ip_address = "127.0.0.1"
    port = 3307
    # create socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # create SSL/TLS context
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
        # allow socket to be re-used
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # bind socket to Cloud SQL proxy server port on localhost
        sock.bind((ip_address, port))
        # listen for incoming connections
        sock.listen(5)

        with context.wrap_socket(sock, server_side=True) as ssock:
            while True:
                conn, _ = ssock.accept()
                conn.close()


@pytest.fixture(scope="session")
def proxy_server(fake_instance: FakeCSQLInstance) -> None:
    """Run local proxy server capable of performing mTLS"""
    thread = Thread(
        target=asyncio.run,
        args=(
            start_proxy_server(
                fake_instance,
            ),
        ),
        daemon=True,
    )
    thread.start()
    thread.join(1.0)  # add a delay to allow the proxy server to start


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
