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
import os
import socket
import asyncio
import pytest  # noqa F401 Needed to run the tests

from threading import Thread
from typing import Any, Generator, AsyncGenerator
from google.auth.credentials import Credentials, with_scopes_if_required
from google.oauth2 import service_account
from aioresponses import aioresponses
from mock import patch

from unit.mocks import FakeCSQLInstance  # type: ignore
from google.cloud.sql.connector import Connector
from google.cloud.sql.connector.instance import Instance
from google.cloud.sql.connector.utils import generate_keys

SCOPES = [
    "https://www.googleapis.com/auth/sqlservice.admin",
    "https://www.googleapis.com/auth/cloud-platform",
]


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
def event_loop() -> asyncio.AbstractEventLoop:
    """
    Creates an event loop to use for testing.
    """
    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    return loop


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
def fake_credentials() -> Credentials:
    fake_service_account = {
        "type": "service_account",
        "project_id": "a-project-id",
        "private_key_id": "a-private-key-id",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDY3E8o1NEFcjMM\nHW/5ZfFJw29/8NEqpViNjQIx95Xx5KDtJ+nWn9+OW0uqsSqKlKGhAdAo+Q6bjx2c\nuXVsXTu7XrZUY5Kltvj94DvUa1wjNXs606r/RxWTJ58bfdC+gLLxBfGnB6CwK0YQ\nxnfpjNbkUfVVzO0MQD7UP0Hl5ZcY0Puvxd/yHuONQn/rIAieTHH1pqgW+zrH/y3c\n59IGThC9PPtugI9ea8RSnVj3PWz1bX2UkCDpy9IRh9LzJLaYYX9RUd7++dULUlat\nAaXBh1U6emUDzhrIsgApjDVtimOPbmQWmX1S60mqQikRpVYZ8u+NDD+LNw+/Eovn\nxCj2Y3z1AgMBAAECggEAWDBzoqO1IvVXjBA2lqId10T6hXmN3j1ifyH+aAqK+FVl\nGjyWjDj0xWQcJ9ync7bQ6fSeTeNGzP0M6kzDU1+w6FgyZqwdmXWI2VmEizRjwk+/\n/uLQUcL7I55Dxn7KUoZs/rZPmQDxmGLoue60Gg6z3yLzVcKiDc7cnhzhdBgDc8vd\nQorNAlqGPRnm3EqKQ6VQp6fyQmCAxrr45kspRXNLddat3AMsuqImDkqGKBmF3Q1y\nxWGe81LphUiRqvqbyUlh6cdSZ8pLBpc9m0c3qWPKs9paqBIvgUPlvOZMqec6x4S6\nChbdkkTRLnbsRr0Yg/nDeEPlkhRBhasXpxpMUBgPywKBgQDs2axNkFjbU94uXvd5\nznUhDVxPFBuxyUHtsJNqW4p/ujLNimGet5E/YthCnQeC2P3Ym7c3fiz68amM6hiA\nOnW7HYPZ+jKFnefpAtjyOOs46AkftEg07T9XjwWNPt8+8l0DYawPoJgbM5iE0L2O\nx8TU1Vs4mXc+ql9F90GzI0x3VwKBgQDqZOOqWw3hTnNT07Ixqnmd3dugV9S7eW6o\nU9OoUgJB4rYTpG+yFqNqbRT8bkx37iKBMEReppqonOqGm4wtuRR6LSLlgcIU9Iwx\nyfH12UWqVmFSHsgZFqM/cK3wGev38h1WBIOx3/djKn7BdlKVh8kWyx6uC8bmV+E6\nOoK0vJD6kwKBgHAySOnROBZlqzkiKW8c+uU2VATtzJSydrWm0J4wUPJifNBa/hVW\ndcqmAzXC9xznt5AVa3wxHBOfyKaE+ig8CSsjNyNZ3vbmr0X04FoV1m91k2TeXNod\njMTobkPThaNm4eLJMN2SQJuaHGTGERWC0l3T18t+/zrDMDCPiSLX1NAvAoGBAN1T\nVLJYdjvIMxf1bm59VYcepbK7HLHFkRq6xMJMZbtG0ryraZjUzYvB4q4VjHk2UDiC\nlhx13tXWDZH7MJtABzjyg+AI7XWSEQs2cBXACos0M4Myc6lU+eL+iA+OuoUOhmrh\nqmT8YYGu76/IBWUSqWuvcpHPpwl7871i4Ga/I3qnAoGBANNkKAcMoeAbJQK7a/Rn\nwPEJB+dPgNDIaboAsh1nZhVhN5cvdvCWuEYgOGCPQLYQF0zmTLcM+sVxOYgfy8mV\nfbNgPgsP5xmu6dw2COBKdtozw0HrWSRjACd1N4yGu75+wPCcX/gQarcjRcXXZeEa\nNtBLSfcqPULqD+h7br9lEJio\n-----END PRIVATE KEY-----\n",
        "client_email": "email@example.com",
        "client_id": "12345",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/email%40example.com",
    }

    fake_credentials = service_account.Credentials.from_service_account_info(
        fake_service_account
    )
    fake_credentials = with_scopes_if_required(fake_credentials, scopes=SCOPES)
    # stub refresh of credentials
    setattr(fake_credentials, "refresh", lambda *args: None)
    return fake_credentials


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
    event_loop: asyncio.AbstractEventLoop,
) -> AsyncGenerator[Instance, None]:
    """
    Instance with mocked API calls.
    """
    # generate client key pair
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), event_loop)
    key_task = asyncio.wrap_future(keys, loop=event_loop)
    _, client_key = await key_task
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        # mock Cloud SQL Admin API calls
        with aioresponses() as mocked:
            mocked.get(
                "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance/connectSettings",
                status=200,
                body=mock_instance.connect_settings(),
                repeat=True,
            )
            mocked.post(
                "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance:generateEphemeralCert",
                status=200,
                body=mock_instance.generate_ephemeral(client_key),
                repeat=True,
            )

            instance = Instance(
                "my-project:my-region:my-instance", "pg8000", keys, event_loop
            )

            yield instance
            await instance.close()


@pytest.fixture
async def connector(fake_credentials: Credentials) -> AsyncGenerator[Connector, None]:
    instance_connection_name = "my-project:my-region:my-instance"
    project, region, instance_name = instance_connection_name.split(":")
    # initialize connector
    connector = Connector()
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        # mock Cloud SQL Admin API calls
        mock_instance = FakeCSQLInstance(project, region, instance_name)
        _, client_key = connector._keys.result()
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
                instance_connection_name, "pg8000", connector._keys, connector._loop
            )

            connector._instances[instance_connection_name] = instance

            yield connector
            connector.close()
