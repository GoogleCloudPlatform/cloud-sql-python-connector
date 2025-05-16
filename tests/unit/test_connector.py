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
from typing import Union

from aiohttp import ClientResponseError
from mock import patch
import pytest  # noqa F401 Needed to run the tests

from google.auth.credentials import Credentials
from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import create_async_connector
from google.cloud.sql.connector import IPTypes
from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError
from google.cloud.sql.connector.exceptions import ClosedConnectorError
from google.cloud.sql.connector.exceptions import IncompatibleDriverError
from google.cloud.sql.connector.instance import RefreshAheadCache


@pytest.mark.asyncio
async def test_connect_enable_iam_auth_error(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that calling connect() with different enable_iam_auth
    argument values creates two cache entries."""
    connect_string = "test-project:test-region:test-instance"
    async with Connector(
        credentials=fake_credentials, loop=asyncio.get_running_loop()
    ) as connector:
        connector._client = fake_client
        # patch db connection creation
        with patch("google.cloud.sql.connector.asyncpg.connect") as mock_connect:
            mock_connect.return_value = True
            # connect with enable_iam_auth False
            connection = await connector.connect_async(
                connect_string,
                "asyncpg",
                user="my-user",
                password="my-pass",
                db="my-db",
                enable_iam_auth=False,
            )
            # verify connector made connection call
            assert connection is True
            # connect with enable_iam_auth True
            connection = await connector.connect_async(
                connect_string,
                "asyncpg",
                user="my-user",
                password="my-pass",
                db="my-db",
                enable_iam_auth=True,
            )
            # verify connector made connection call
            assert connection is True
            # verify both cache entries for same instance exist
            assert len(connector._cache) == 2
            assert (connect_string, True) in connector._cache
            assert (connect_string, False) in connector._cache


async def test_connect_incompatible_driver_error(
    fake_credentials: Credentials,
    fake_client: CloudSQLClient,
) -> None:
    """Test that calling connect() with driver that is incompatible with
    database version throws error."""
    connect_string = "test-project:test-region:test-instance"
    async with Connector(
        credentials=fake_credentials, loop=asyncio.get_running_loop()
    ) as connector:
        connector._client = fake_client
        # try to connect using pymysql driver to a Postgres database
        with pytest.raises(IncompatibleDriverError) as exc_info:
            await connector.connect_async(connect_string, "pymysql")
        assert (
            exc_info.value.args[0]
            == "Database driver 'pymysql' is incompatible with database version"
            " 'POSTGRES_15'. Given driver can only be used with Cloud SQL MYSQL"
            " databases."
        )


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


def test_Connector_Init_with_lazy_refresh(fake_credentials: Credentials) -> None:
    """Test that Connector with lazy refresh sets keys to None."""
    with Connector(credentials=fake_credentials, refresh_strategy="lazy") as connector:
        assert connector._keys is None


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
    "ip_type, expected",
    [
        (
            "private",
            IPTypes.PRIVATE,
        ),
        (
            "PRIVATE",
            IPTypes.PRIVATE,
        ),
        (
            IPTypes.PRIVATE,
            IPTypes.PRIVATE,
        ),
        (
            "public",
            IPTypes.PUBLIC,
        ),
        (
            "PUBLIC",
            IPTypes.PUBLIC,
        ),
        (
            IPTypes.PUBLIC,
            IPTypes.PUBLIC,
        ),
        (
            "psc",
            IPTypes.PSC,
        ),
        (
            "PSC",
            IPTypes.PSC,
        ),
        (
            IPTypes.PSC,
            IPTypes.PSC,
        ),
    ],
)
def test_Connector_init_ip_type(
    ip_type: Union[str, IPTypes], expected: IPTypes, fake_credentials: Credentials
) -> None:
    """
    Test to check whether the __init__ method of Connector
    properly sets ip_type.
    """
    connector = Connector(credentials=fake_credentials, ip_type=ip_type)
    assert connector._ip_type == expected
    connector.close()


def test_Connector_Init_bad_ip_type(fake_credentials: Credentials) -> None:
    """Test that Connector errors due to bad ip_type str."""
    bad_ip_type = "bad-ip-type"
    with pytest.raises(ValueError) as exc_info:
        Connector(ip_type=bad_ip_type, credentials=fake_credentials)
    assert (
        exc_info.value.args[0]
        == f"Incorrect value for ip_type, got '{bad_ip_type.upper()}'. "
        "Want one of: 'PRIMARY', 'PRIVATE', 'PSC', 'PUBLIC'."
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
            == f"Incorrect value for ip_type, got '{bad_ip_type.upper()}'. "
            "Want one of: 'PRIMARY', 'PRIVATE', 'PSC', 'PUBLIC'."
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


async def test_Connector_remove_cached_bad_instance(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """When a Connector attempts to retrieve connection info for a
    non-existent instance, it should delete the instance from
    the cache and ensure no background refresh happens (which would be
    wasted cycles).
    """
    async with Connector(
        credentials=fake_credentials, loop=asyncio.get_running_loop()
    ) as connector:
        conn_name = ConnectionName("bad-project", "bad-region", "bad-inst")
        # populate cache
        cache = RefreshAheadCache(conn_name, fake_client, connector._keys)
        connector._cache[(str(conn_name), False)] = cache
        # aiohttp client should throw a 404 ClientResponseError
        with pytest.raises(ClientResponseError):
            await connector.connect_async(
                str(conn_name),
                "pg8000",
            )
        # check that cache has been removed from dict
        assert (str(conn_name), False) not in connector._cache


async def test_Connector_remove_cached_no_ip_type(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """When a Connector attempts to connect and preferred IP type is not present,
    it should delete the instance from the cache and ensure no background refresh
    happens (which would be wasted cycles).
    """
    # set instance to only have public IP
    fake_client.instance.ip_addrs = {"PRIMARY": "127.0.0.1"}
    async with Connector(
        credentials=fake_credentials, loop=asyncio.get_running_loop()
    ) as connector:
        conn_name = ConnectionName("test-project", "test-region", "test-instance")
        # populate cache
        cache = RefreshAheadCache(conn_name, fake_client, connector._keys)
        connector._cache[(str(conn_name), False)] = cache
        # test instance does not have Private IP, thus should invalidate cache
        with pytest.raises(CloudSQLIPTypeError):
            await connector.connect_async(
                str(conn_name),
                "pg8000",
                user="my-user",
                password="my-pass",
                ip_type="private",
            )
        # check that cache has been removed from dict
        assert (str(conn_name), False) not in connector._cache


def test_default_universe_domain(fake_credentials: Credentials) -> None:
    """Test that default universe domain and constructed service endpoint are
    formatted correctly.
    """
    with Connector(credentials=fake_credentials) as connector:
        # test universe domain was not configured
        assert connector._universe_domain is None
        # test property and service endpoint construction
        assert connector.universe_domain == "googleapis.com"
        assert connector._sqladmin_api_endpoint == "https://sqladmin.googleapis.com"


def test_configured_universe_domain_matches_GDU(fake_credentials: Credentials) -> None:
    """Test that configured universe domain succeeds with matched GDU credentials."""
    universe_domain = "googleapis.com"
    with Connector(
        credentials=fake_credentials, universe_domain=universe_domain
    ) as connector:
        # test universe domain was configured
        assert connector._universe_domain == universe_domain
        # test property and service endpoint construction
        assert connector.universe_domain == universe_domain
        assert connector._sqladmin_api_endpoint == f"https://sqladmin.{universe_domain}"


def test_configured_universe_domain_matches_credentials(
    fake_credentials: Credentials,
) -> None:
    """Test that configured universe domain succeeds with matching universe
    domain credentials.
    """
    universe_domain = "test-universe.test"
    # set fake credentials to be configured for the universe domain
    fake_credentials._universe_domain = universe_domain
    with Connector(
        credentials=fake_credentials, universe_domain=universe_domain
    ) as connector:
        # test universe domain was configured
        assert connector._universe_domain == universe_domain
        # test property and service endpoint construction
        assert connector.universe_domain == universe_domain
        assert connector._sqladmin_api_endpoint == f"https://sqladmin.{universe_domain}"


def test_configured_universe_domain_mismatched_credentials(
    fake_credentials: Credentials,
) -> None:
    """Test that configured universe domain errors with mismatched universe
    domain credentials.
    """
    universe_domain = "test-universe.test"
    # credentials have GDU domain ("googleapis.com")
    with pytest.raises(ValueError) as exc_info:
        Connector(credentials=fake_credentials, universe_domain=universe_domain)
    err_msg = (
        f"The configured universe domain ({universe_domain}) does "
        "not match the universe domain found in the credentials "
        f"({fake_credentials.universe_domain}). If you haven't "
        "configured the universe domain explicitly, `googleapis.com` "
        "is the default."
    )
    assert exc_info.value.args[0] == err_msg


def test_configured_universe_domain_env_var(
    fake_credentials: Credentials,
) -> None:
    """Test that configured universe domain succeeds with universe
    domain set via GOOGLE_CLOUD_UNIVERSE_DOMAIN env var.
    """
    universe_domain = "test-universe.test"
    # set fake credentials to be configured for the universe domain
    fake_credentials._universe_domain = universe_domain
    # set environment variable
    os.environ["GOOGLE_CLOUD_UNIVERSE_DOMAIN"] = universe_domain
    # Note: we are not passing universe_domain arg, env var should set it
    with Connector(credentials=fake_credentials) as connector:
        # test universe domain was configured
        assert connector._universe_domain == universe_domain
        # test property and service endpoint construction
        assert connector.universe_domain == universe_domain
        assert connector._sqladmin_api_endpoint == f"https://sqladmin.{universe_domain}"
    # unset env var
    del os.environ["GOOGLE_CLOUD_UNIVERSE_DOMAIN"]


def test_configured_quota_project_env_var(
    fake_credentials: Credentials,
) -> None:
    """Test that configured quota project succeeds with quota project
    set via GOOGLE_CLOUD_QUOTA_PROJECT env var.
    """
    quota_project = "my-cool-project"
    # set environment variable
    os.environ["GOOGLE_CLOUD_QUOTA_PROJECT"] = quota_project
    # Note: we are not passing quota_project arg, env var should set it
    with Connector(credentials=fake_credentials) as connector:
        # test quota project was configured
        assert connector._quota_project == quota_project
    # unset env var
    del os.environ["GOOGLE_CLOUD_QUOTA_PROJECT"]


@pytest.mark.asyncio
async def test_connect_async_closed_connector(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that calling connect_async() on a closed connector raises an error."""
    async with Connector(
        credentials=fake_credentials, loop=asyncio.get_running_loop()
    ) as connector:
        connector._client = fake_client
        await connector.close_async()
        with pytest.raises(ClosedConnectorError) as exc_info:
            await connector.connect_async(
                "test-project:test-region:test-instance",
                "asyncpg",
                user="my-user",
                password="my-pass",
                db="my-db",
            )
        assert (
            exc_info.value.args[0]
            == "Connection attempt failed because the connector has already been closed."
        )


def test_connect_closed_connector(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that calling connect() on a closed connector raises an error."""
    with Connector(credentials=fake_credentials) as connector:
        connector._client = fake_client
        connector.close()
        with pytest.raises(ClosedConnectorError) as exc_info:
            connector.connect(
                "test-project:test-region:test-instance",
                "pg8000",
                user="my-user",
                password="my-pass",
                db="my-db",
            )
        assert (
            exc_info.value.args[0]
            == "Connection attempt failed because the connector has already been closed."
        )
