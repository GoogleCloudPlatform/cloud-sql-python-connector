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
from typing import Any, AsyncGenerator, Generator, Tuple

from aioresponses import aioresponses
from google.auth.credentials import Credentials
import pytest  # noqa F401 Needed to run the tests
from unit.mocks import FakeCredentials  # type: ignore
from unit.mocks import FakeCSQLInstance  # type: ignore

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector.instance import Instance
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


@pytest.fixture(scope="module")
def mock_instance() -> FakeCSQLInstance:
    mock_instance = FakeCSQLInstance("my-project", "my-region", "my-instance")
    return mock_instance


@pytest.fixture
async def instance(
    mock_instance: FakeCSQLInstance,
    fake_credentials: Credentials,
) -> AsyncGenerator[Instance, None]:
    """
    Instance with mocked API calls.
    """
    loop = asyncio.get_running_loop()
    # generate client key pair
    keys = asyncio.create_task(generate_keys())
    _, client_key = await keys

    # mock Cloud SQL Admin API calls
    with aioresponses() as mocked:
        mocked.get(
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{mock_instance.project}/instances/{mock_instance.name}/connectSettings",
            status=200,
            body=mock_instance.connect_settings(),
            repeat=True,
        )
        mocked.post(
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{mock_instance.project}/instances/{mock_instance.name}:generateEphemeralCert",
            status=200,
            body=mock_instance.generate_ephemeral(client_key),
            repeat=True,
        )

        instance = Instance(
            f"{mock_instance.project}:{mock_instance.region}:{mock_instance.name}",
            "pg8000",
            keys,
            loop,
            fake_credentials,
        )

        yield instance
        await instance.close()


@pytest.fixture
async def connector(fake_credentials: Credentials) -> AsyncGenerator[Connector, None]:
    instance_connection_name = "my-project:my-region:my-instance"
    project, region, instance_name = instance_connection_name.split(":")
    # initialize connector
    connector = Connector(credentials=fake_credentials)
    # mock Cloud SQL Admin API calls
    mock_instance = FakeCSQLInstance(project, region, instance_name)

    async def wait_for_keys(future: asyncio.Future) -> Tuple[bytes, str]:
        """
        Helper method to await keys of Connector in tests prior to
        initializing an Instance object.
        """
        return await future

    # converting asyncio.Future into concurrent.Future
    # await keys in background thread so that .result() is set
    # required because keys are needed for mocks, but are not awaited
    # in the code until Instance() is initialized
    _, client_key = asyncio.run_coroutine_threadsafe(
        wait_for_keys(connector._keys), connector._loop
    ).result()
    with aioresponses() as mocked:
        mocked.get(
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{project}/instances/{instance_name}/connectSettings",
            status=200,
            body=mock_instance.connect_settings(),
            repeat=True,
        )
        mocked.post(
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{project}/instances/{instance_name}:generateEphemeralCert",
            status=200,
            body=mock_instance.generate_ephemeral(client_key),
            repeat=True,
        )
        # initialize Instance using mocked API calls
        instance = Instance(
            instance_connection_name,
            "pg8000",
            connector._keys,
            connector._loop,
            fake_credentials,
        )

        connector._instances[instance_connection_name] = instance

        yield connector
        connector.close()
