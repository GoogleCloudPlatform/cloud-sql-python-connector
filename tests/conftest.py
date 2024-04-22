""""
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
from threading import Thread
from typing import Any, AsyncGenerator, Generator

from aiohttp import web
import pytest  # noqa F401 Needed to run the tests
from unit.mocks import FakeCredentials  # type: ignore
from unit.mocks import FakeCSQLInstance  # type: ignore

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.instance import RefreshAheadCache
from google.cloud.sql.connector.utils import generate_keys

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


def mock_server(server_sock: socket.socket) -> None:
    """Create mock server listening on specified ip_address and port."""
    ip_address = "127.0.0.1"
    port = 3307
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((ip_address, port))
    server_sock.listen(0)
    server_sock.accept()


@pytest.fixture
def server() -> Generator:
    """Create thread with server listening on proper port"""
    server_sock = socket.socket()
    thread = Thread(target=mock_server, args=(server_sock,), daemon=True)
    thread.start()
    yield thread
    server_sock.close()
    thread.join()


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
    return CloudSQLClient("", "", fake_credentials, client=client_session)


@pytest.fixture
async def cache(fake_client: CloudSQLClient) -> AsyncGenerator[RefreshAheadCache, None]:
    keys = asyncio.create_task(generate_keys())
    cache = RefreshAheadCache(
        "test-project:test-region:test-instance",
        client=fake_client,
        keys=keys,
    )
    yield cache
    await cache.close()
