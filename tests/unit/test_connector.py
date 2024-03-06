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

from google.auth.credentials import Credentials
from mock import patch
import pytest  # noqa F401 Needed to run the tests

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import create_async_connector
from google.cloud.sql.connector import IPTypes
from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.exceptions import ConnectorLoopError
from google.cloud.sql.connector.instance import Instance


def test_connect_enable_iam_auth_error(
    fake_credentials: Credentials, instance: Instance
) -> None:
    """Test that calling connect() with different enable_iam_auth
    argument values throws error."""
    connect_string = "test-project:test-region:test-instance"
    connector = Connector(credentials=fake_credentials)
    # set instance
    connector._instances[connect_string] = instance
    # try to connect using enable_iam_auth=True, should raise error
    with pytest.raises(ValueError) as exc_info:
        connector.connect(connect_string, "pg8000", enable_iam_auth=True)
    assert (
        exc_info.value.args[0] == "connect() called with 'enable_iam_auth=True', "
        "but previously used 'enable_iam_auth=False'. "
        "If you require both for your use case, please use a new "
        "connector.Connector object."
    )
    # remove instance to avoid destructor warnings
    connector._instances = {}


def test_connect_with_unsupported_driver(fake_credentials: Credentials) -> None:
    with Connector(credentials=fake_credentials) as connector:
        # try to connect using unsupported driver, should raise KeyError
        with pytest.raises(KeyError) as exc_info:
            connector.connect(
                "my-project:my-region:my-instance",
                "bad_driver",
            )
        # assert custom error message for unsupported driver is present
        assert exc_info.value.args[0] == "Driver 'bad_driver' is not supported."


@pytest.mark.asyncio
async def test_connect_ConnectorLoopError(fake_credentials: Credentials) -> None:
    """Test that ConnectorLoopError is thrown when Connector.connect
    is called with event loop running in current thread."""
    current_loop = asyncio.get_running_loop()
    connector = Connector(credentials=fake_credentials, loop=current_loop)
    # try to connect using current thread's loop, should raise error
    pytest.raises(
        ConnectorLoopError,
        connector.connect,
        "my-project:my-region:my-instance",
        "pg8000",
    )


def test_Connector_Init(fake_credentials: Credentials) -> None:
    """Test that Connector __init__ sets default properties properly."""
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        connector = Connector()
        assert connector._ip_type == IPTypes.PUBLIC
        assert connector._enable_iam_auth is False
        assert connector._timeout == 30
        assert connector._credentials == fake_credentials
        mock_auth.assert_called_once()
        connector.close()


def test_Connector_Init_with_credentials(fake_credentials: Credentials) -> None:
    """Test that Connector uses custom credentials when given them."""
    with patch(
        "google.cloud.sql.connector.connector.with_scopes_if_required"
    ) as mock_auth:
        mock_auth.return_value = fake_credentials
        connector = Connector(credentials=fake_credentials)
        assert connector._credentials == fake_credentials
        mock_auth.assert_called_once()
        connector.close()


def test_Connector_Init_with_bad_credentials_type() -> None:
    """Test that Connector with bad custom credentials type throws error."""
    pytest.raises(TypeError, Connector, credentials="bad creds")


def test_Connector_Init_context_manager(fake_credentials: Credentials) -> None:
    """Test that Connector as context manager sets default properties properly."""
    with Connector(credentials=fake_credentials) as connector:
        assert connector._ip_type == IPTypes.PUBLIC
        assert connector._enable_iam_auth is False
        assert connector._timeout == 30
        assert connector._credentials == fake_credentials


@pytest.mark.asyncio
async def test_Connector_Init_async_context_manager(
    fake_credentials: Credentials,
) -> None:
    """Test that Connector as async context manager sets default properties
    properly."""
    loop = asyncio.get_running_loop()
    async with Connector(credentials=fake_credentials, loop=loop) as connector:
        assert connector._ip_type == IPTypes.PUBLIC
        assert connector._enable_iam_auth is False
        assert connector._timeout == 30
        assert connector._credentials == fake_credentials
        assert connector._loop == loop


@pytest.mark.parametrize(
    "ip_type",
    ["public", "private", "psc", "PUBLIC", "PRIVATE", "PSC"],
)
def test_Connector_Init_ip_type_str(
    ip_type: str, fake_credentials: Credentials
) -> None:
    """Test that Connector properly sets ip_type when given str."""
    with Connector(ip_type=ip_type, credentials=fake_credentials) as connector:
        if ip_type.lower() == "public":
            assert connector._ip_type == IPTypes.PUBLIC
        if ip_type.lower() == "private":
            assert connector._ip_type == IPTypes.PRIVATE
        if ip_type.lower() == "psc":
            assert connector._ip_type == IPTypes.PSC


def test_Connector_Init_bad_ip_type(fake_credentials: Credentials) -> None:
    """Test that Connector errors due to bad ip_type str."""
    bad_ip_type = "bad-ip-type"
    with pytest.raises(ValueError) as exc_info:
        Connector(ip_type=bad_ip_type, credentials=fake_credentials)
    assert (
        exc_info.value.args[0]
        == f"Incorrect value for ip_type, got '{bad_ip_type}'. Want one of: 'public', 'private' or 'psc'."
    )


def test_Connector_connect_bad_ip_type(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that Connector.connect errors due to bad ip_type str."""
    with Connector(credentials=fake_credentials) as connector:
        connector._client = fake_client
        bad_ip_type = "bad-ip-type"
        with pytest.raises(ValueError) as exc_info:
            connector.connect(
                "test-project:test-region:test-instance",
                "pg8000",
                user="my-user",
                password="my-pass",
                db="my-db",
                ip_type=bad_ip_type,
            )
        assert (
            exc_info.value.args[0]
            == f"Incorrect value for ip_type, got '{bad_ip_type}'. Want one of: 'public', 'private' or 'psc'."
        )


@pytest.mark.asyncio
async def test_Connector_connect_async(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that Connector.connect_async can properly return a DB API connection."""
    async with Connector(
        credentials=fake_credentials, loop=asyncio.get_running_loop()
    ) as connector:
        connector._client = fake_client
        # patch db connection creation
        with patch("google.cloud.sql.connector.asyncpg.connect") as mock_connect:
            mock_connect.return_value = True
            connection = await connector.connect_async(
                "test-project:test-region:test-instance",
                "asyncpg",
                user="my-user",
                password="my-pass",
                db="my-db",
            )
            # verify connector made connection call
            assert connection is True


@pytest.mark.asyncio
async def test_create_async_connector(fake_credentials: Credentials) -> None:
    """Test that create_async_connector properly initializes connector
    object using current thread's event loop"""
    connector = await create_async_connector(credentials=fake_credentials)
    assert connector._loop == asyncio.get_running_loop()
    await connector.close_async()


def test_Connector_close_kills_thread(fake_credentials: Credentials) -> None:
    """Test that Connector.close kills background threads."""
    # open and close Connector object
    connector = Connector(credentials=fake_credentials)
    # verify background thread exists
    assert connector._thread
    connector.close()
    # check that connector thread is no longer running
    assert connector._thread.is_alive() is False


def test_Connector_close_called_multiple_times(fake_credentials: Credentials) -> None:
    """Test that Connector.close can be called multiple times."""
    # open and close Connector object
    connector = Connector(credentials=fake_credentials)
    # verify background thread exists
    assert connector._thread
    connector.close()
    # check that connector thread is no longer running
    assert connector._thread.is_alive() is False
    # call connector.close a second time
    connector.close()
