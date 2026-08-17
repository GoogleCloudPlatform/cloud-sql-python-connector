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
from __future__ import annotations

import asyncio
import os
from threading import Thread
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from aiohttp import ClientResponseError
from google.auth.credentials import Credentials
import pytest

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import create_async_connector
from google.cloud.sql.connector import IPTypes
from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import ClosedConnectorError
from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError
from google.cloud.sql.connector.exceptions import ConnectorLoopError
from google.cloud.sql.connector.exceptions import IncompatibleDriverError
from google.cloud.sql.connector.instance import RefreshAheadCache
from google.cloud.sql.connector.resolver import DnsResolver
from google.cloud.sql.connector.sqldata_client import FallbackSocket
from google.cloud.sql.connector.sqldata_client import SqlDataClient


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
        (
            "sqldata",
            IPTypes.SQL_DATA,
        ),
        (
            "SQLDATA",
            IPTypes.SQL_DATA,
        ),
        (
            "SQL_DATA",
            IPTypes.SQL_DATA,
        ),
        (
            IPTypes.SQL_DATA,
            IPTypes.SQL_DATA,
        ),
    ],
)
def test_Connector_init_ip_type(
    ip_type: str | IPTypes, expected: IPTypes, fake_credentials: Credentials
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
        "Want one of: 'PRIMARY', 'PRIVATE', 'PSC', 'SQL_DATA', 'PUBLIC'."
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
            "Want one of: 'PRIMARY', 'PRIVATE', 'PSC', 'SQL_DATA', 'PUBLIC'."
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
async def test_Connector_connect_async_multiple_event_loops(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that Connector.connect_async errors when run on wrong event loop."""

    new_loop = asyncio.new_event_loop()
    thread = Thread(target=new_loop.run_forever, daemon=True)
    thread.start()

    async with Connector(
        credentials=fake_credentials, loop=asyncio.get_running_loop()
    ) as connector:
        connector._client = fake_client
        with pytest.raises(ConnectorLoopError) as exc_info:
            future = asyncio.run_coroutine_threadsafe(
                connector.connect_async(
                    "test-project:test-region:test-instance", "asyncpg"
                ),
                loop=new_loop,
            )
            future.result()
        assert (
            exc_info.value.args[0] == "Running event loop does not match "
            "'connector._loop'. Connector.connect_async() must be called from "
            "the event loop the Connector was initialized with. If you need to "
            "connect across event loops, please use a new Connector object."
        )
    new_loop.call_soon_threadsafe(new_loop.stop)
    thread.join()


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


@pytest.mark.asyncio
async def test_Connector_connect_async_custom_dns_resolver(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that Connector.connect_async uses custom DNS name resolution."""

    # Create a mock DnsResolver that returns a fixed IP
    with patch(
        "google.cloud.sql.connector.resolver.DnsResolver.resolve_a_record"
    ) as mock_resolve_a:
        mock_resolve_a.return_value = ["1.2.3.4"]

        # We also need to patch resolve because DnsResolver.resolve does DNS lookup for TXT
        # But we can patch DnsResolver.resolve to return a ConnectionName with domain name
        with patch(
            "google.cloud.sql.connector.resolver.DnsResolver.resolve"
        ) as mock_resolve:
            # This must return a ConnectionName object with domain_name set
            conn_name_with_domain = ConnectionName(
                "test-project", "test-region", "test-instance", "db.example.com"
            )
            mock_resolve.return_value = conn_name_with_domain

            async with Connector(
                credentials=fake_credentials,
                loop=asyncio.get_running_loop(),
                resolver=DnsResolver,
            ) as connector:
                connector._client = fake_client

                # patch db connection creation
                with patch(
                    "google.cloud.sql.connector.asyncpg.connect"
                ) as mock_connect:
                    mock_connect.return_value = True

                    # Call connect_async
                    # Use "db.example.com" as instance connection string (resolver will handle it)
                    connection = await connector.connect_async(
                        "db.example.com",
                        "asyncpg",
                        user="my-user",
                        password="my-pass",
                        db="my-db",
                    )

                    # Verify mock_connect was called with resolved IP "1.2.3.4"
                    # The first arg to mock_connect (which patches connector call) is ip_address
                    args, _ = mock_connect.call_args
                    assert args[0] == "1.2.3.4"
                    assert connection is True


@pytest.mark.asyncio
async def test_Connector_connect_async_custom_dns_resolver_fallback(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that Connector.connect_async falls back if DNS resolution fails."""

    # Create a mock DnsResolver that returns empty list (failure)
    with patch(
        "google.cloud.sql.connector.resolver.DnsResolver.resolve_a_record"
    ) as mock_resolve_a:
        mock_resolve_a.return_value = []

        with patch(
            "google.cloud.sql.connector.resolver.DnsResolver.resolve"
        ) as mock_resolve:
            conn_name_with_domain = ConnectionName(
                "test-project", "test-region", "test-instance", "db.example.com"
            )
            mock_resolve.return_value = conn_name_with_domain

            async with Connector(
                credentials=fake_credentials,
                loop=asyncio.get_running_loop(),
                resolver=DnsResolver,
            ) as connector:
                connector._client = fake_client

                # Save original IPs to restore later (fake_instance is session-scoped)
                original_ips = fake_client.instance.ip_addrs
                # Set metadata IP to something specific
                fake_client.instance.ip_addrs = {"PRIMARY": "5.6.7.8"}

                try:
                    with patch(
                        "google.cloud.sql.connector.asyncpg.connect"
                    ) as mock_connect:
                        mock_connect.return_value = True

                        connection = await connector.connect_async(
                            "db.example.com",
                            "asyncpg",
                            user="my-user",
                            password="my-pass",
                            db="my-db",
                        )

                        # Verify mock_connect was called with metadata IP "5.6.7.8"
                        args, _ = mock_connect.call_args
                        assert args[0] == "5.6.7.8"
                        assert connection is True
                finally:
                    # Restore original IPs
                    fake_client.instance.ip_addrs = original_ips


@pytest.mark.asyncio
async def test_Connector_connect_async_custom_dns_resolver_no_fallback_psc_to_private_ip(
    fake_credentials: Credentials, fake_client: CloudSQLClient
) -> None:
    """Test that Connector.connect_async does not fall back to Private IP if CNAME/PSC DNS resolution fails."""

    with patch(
        "google.cloud.sql.connector.resolver.DnsResolver.resolve_a_record"
    ) as mock_resolve_a:
        # DNS resolution fails
        mock_resolve_a.return_value = []

        with patch(
            "google.cloud.sql.connector.resolver.DnsResolver.resolve"
        ) as mock_resolve:
            conn_name_with_domain = ConnectionName(
                "test-project", "test-region", "test-instance", "db.example.com"
            )
            mock_resolve.return_value = conn_name_with_domain

            async with Connector(
                credentials=fake_credentials,
                loop=asyncio.get_running_loop(),
                resolver=DnsResolver,
                ip_type="PSC",  # Use PSC IP type
            ) as connector:
                connector._client = fake_client

                original_ips = fake_client.instance.ip_addrs
                original_dns_names = fake_client.instance.dns_names
                # Configure instance to be PSC enabled, but also have a PRIVATE IP!
                fake_client.instance.psc_enabled = True
                fake_client.instance.dns_names = ["1ad3b5d73f10.3oxon2yfo9tob.us-east1.sql.goog"]
                fake_client.instance.ip_addrs = {
                    "PSC": "1ad3b5d73f10.3oxon2yfo9tob.us-east1.sql.goog",
                    "PRIVATE": "10.0.0.1",
                }

                try:
                    with patch(
                        "google.cloud.sql.connector.asyncpg.connect"
                    ) as mock_connect:
                        mock_connect.return_value = True

                        connection = await connector.connect_async(
                            "db.example.com",
                            "asyncpg",
                            user="my-user",
                            password="my-pass",
                            db="my-db",
                        )

                        # Verify mock_connect used PSC DNS instead of falling back to PRIVATE IP "10.0.0.1"!
                        args, _ = mock_connect.call_args
                        assert args[0] == "1ad3b5d73f10.3oxon2yfo9tob.us-east1.sql.goog"
                        assert connection is True
                finally:
                    # Restore original IPs and DNS names
                    fake_client.instance.ip_addrs = original_ips
                    fake_client.instance.dns_names = original_dns_names
                    fake_client.instance.psc_enabled = False


def test_Connector_Init_sqldata_options(fake_credentials: Credentials) -> None:
    """Test that Connector initializes with custom SQL data endpoint and timeout."""
    with Connector(
        credentials=fake_credentials,
        sql_data_endpoint="custom.sqladmin.googleapis.com",
        sql_data_stream_timeout=3600,
    ) as connector:
        assert connector._sql_data_endpoint == "custom.sqladmin.googleapis.com"
        assert connector._sql_data_stream_timeout == 3600


@pytest.mark.asyncio
async def test_create_async_connector_sqldata_options(
    fake_credentials: Credentials,
) -> None:
    """Test that create_async_connector properly forwards SQL data options."""
    connector = await create_async_connector(
        credentials=fake_credentials,
        sql_data_endpoint="custom.sqladmin.googleapis.com",
        sql_data_stream_timeout=1800,
    )
    assert connector._sql_data_endpoint == "custom.sqladmin.googleapis.com"
    assert connector._sql_data_stream_timeout == 1800
    await connector.close_async()


@pytest.mark.asyncio
async def test_Connector_connect_async_sqldata_iam_auth(
    fake_credentials: Credentials,
    fake_client: CloudSQLClient,
) -> None:
    """Test that connect_async with SQL_DATA and IAM auth properly maps driver engine without KeyError."""
    connect_string = "test-project:test-region:test-instance"
    async with Connector(
        credentials=fake_credentials,
        loop=asyncio.get_running_loop(),
        ip_type=IPTypes.SQL_DATA,
    ) as connector:
        connector._client = fake_client

        with patch("google.cloud.sql.connector.connector.SqlDataClient") as mock_sqldata_cls:
            mock_client_instance = MagicMock()
            mock_client_instance.connect_tunnel = AsyncMock(return_value=3307)
            mock_client_instance.close = AsyncMock()
            mock_sqldata_cls.return_value = mock_client_instance

            with patch("google.cloud.sql.connector.asyncpg.connect") as mock_connect:
                mock_connect.return_value = True

                connection = await connector.connect_async(
                    connect_string,
                    "asyncpg",
                    user="test-sa@test-project.iam.gserviceaccount.com",
                    db="my-db",
                    enable_iam_auth=True,
                )
                assert connection is True
                # Verify IAM user was formatted and passed without error
                assert mock_connect.called
                _, kwargs = mock_connect.call_args
                assert kwargs["user"] == "test-sa@test-project.iam"


def test_sqldata_client_init(fake_credentials: Credentials) -> None:
    """Test that SqlDataClient initializes with expected properties."""
    client = SqlDataClient(
        endpoint="custom.sqladmin.googleapis.com",
        credentials=fake_credentials,
        quota_project="test-quota-project",
        timeout=3600,
    )
    assert client._endpoint == "custom.sqladmin.googleapis.com"
    assert client._credentials == fake_credentials
    assert client._quota_project == "test-quota-project"
    assert client._timeout == 3600
    assert client._server is None
    assert len(client._tunnel_tasks) == 0


@pytest.mark.asyncio
async def test_sqldata_client_close(fake_credentials: Credentials) -> None:
    """Test that SqlDataClient.close cleanly cancels tasks and closes resources."""
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=fake_credentials,
    )
    mock_server = MagicMock()
    mock_server.close = MagicMock()
    mock_server.wait_closed = AsyncMock()
    client._server = mock_server

    mock_channel = AsyncMock()
    client._active_grpc_channels.add(mock_channel)

    mock_writer = MagicMock()
    client._active_writers.add(mock_writer)

    callback_called = False

    def on_close() -> None:
        nonlocal callback_called
        callback_called = True

    client._on_close_callbacks.append(on_close)

    async def dummy_task():
        await asyncio.sleep(100)

    task = asyncio.create_task(dummy_task())
    client._tunnel_tasks.add(task)

    await client.close()

    try:
        await task
    except asyncio.CancelledError:
        pass

    assert client._server is None
    assert mock_server.close.called
    assert mock_channel.close.called
    assert mock_writer.close.called
    assert task.cancelled()
    assert callback_called


def test_fallback_socket() -> None:
    """Test that FallbackSocket ignores connect calls."""
    sock = FallbackSocket()
    sock.connect("127.0.0.1", 3307)
    sock.close()


@pytest.mark.asyncio
async def test_sqldata_client_connect_tunnel(fake_credentials: Credentials) -> None:
    """Test that connect_tunnel binds to a local port."""
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=fake_credentials,
    )
    get_conn_info = AsyncMock()
    on_fallback = MagicMock()
    is_fallback_cached = MagicMock(return_value=False)

    port = await client.connect_tunnel(
        instance_connection_name="proj:reg:inst",
        region="reg",
        project="proj",
        get_conn_info=get_conn_info,
        enable_iam_auth=False,
        on_fallback=on_fallback,
        is_fallback_cached=is_fallback_cached,
    )
    assert isinstance(port, int)
    assert port > 0
    await client.close()


def test_Connector_Init_resource_exhausted_options(
    fake_credentials: Credentials,
) -> None:
    """Test that Connector initializes with resource_exhausted_cooldown_period."""
    with Connector(
        credentials=fake_credentials,
        resource_exhausted_cooldown_period=10.0,
    ) as connector:
        assert connector._resource_exhausted_cooldown_period == 10.0


@pytest.mark.asyncio
async def test_create_async_connector_resource_exhausted_options(
    fake_credentials: Credentials,
) -> None:
    """Test that create_async_connector forwards resource_exhausted_cooldown_period."""
    connector = await create_async_connector(
        credentials=fake_credentials,
        resource_exhausted_cooldown_period=8.5,
    )
    assert connector._resource_exhausted_cooldown_period == 8.5
    await connector.close_async()


def test_cooldown_backoff_calculation() -> None:
    """Test exponential backoff with jitter calculation."""
    from google.cloud.sql.connector.connector import _cooldown_backoff

    base = 5.0
    for attempt in range(1, 6):
        backoff = _cooldown_backoff(base, attempt)
        # 1.618^(attempt-1) <= multiplier <= 1.618^attempt
        min_expected = base * (1.618 ** (attempt - 1))
        max_expected = base * (1.618**attempt)
        assert min_expected <= backoff <= max_expected


def test_is_resource_exhausted_error_helper() -> None:
    """Test is_resource_exhausted_error helper with various exception types."""
    import grpc

    from google.cloud.sql.connector.sqldata_client import is_resource_exhausted_error

    class MockRpcError(Exception):
        def __init__(self, code):
            self._code = code

        def code(self):
            return self._code

    assert is_resource_exhausted_error(
        MockRpcError(grpc.StatusCode.RESOURCE_EXHAUSTED)
    )
    assert not is_resource_exhausted_error(
        MockRpcError(grpc.StatusCode.FAILED_PRECONDITION)
    )
    assert not is_resource_exhausted_error(Exception("other error"))


@pytest.mark.asyncio
async def test_ResourceExhausted_cooldown_blocks_connection(
    fake_credentials: Credentials,
    fake_client: CloudSQLClient,
) -> None:
    """Test that active cooldown raises ResourceExhaustedError without connecting."""
    import time

    from google.cloud.sql.connector.connector import SqlDataConnState
    from google.cloud.sql.connector.exceptions import ResourceExhaustedError

    connect_string = "proj:reg:inst"
    async with Connector(
        credentials=fake_credentials,
        loop=asyncio.get_running_loop(),
        ip_type=IPTypes.SQL_DATA,
        resource_exhausted_cooldown_period=2.0,
    ) as connector:
        connector._client = fake_client

        # Manually set state to cooldown active
        state = SqlDataConnState()
        state.cooldown_until = time.time() + 10.0
        state.backoff_counter = 1
        state.last_err = Exception("resource busy")
        connector._sql_data_conn_state[connect_string] = state

        with (
            patch(
                "google.cloud.sql.connector.connector.SqlDataClient"
            ) as mock_sqldata_cls,
            pytest.raises(ResourceExhaustedError) as exc_info,
        ):
            await connector.connect_async(
                connect_string,
                "asyncpg",
                user="test-user",
                db="test-db",
            )
        assert "cooldown active" in str(exc_info.value)
        assert not mock_sqldata_cls.called


@pytest.mark.asyncio
async def test_ResourceExhausted_callbacks_lifecycle(
    fake_credentials: Credentials,
    fake_client: CloudSQLClient,
) -> None:
    """Test that on_resource_exhausted and on_success callbacks properly update state."""
    import time

    from google.cloud.sql.connector.exceptions import ResourceExhaustedError

    connect_string = "proj:reg:inst"
    async with Connector(
        credentials=fake_credentials,
        loop=asyncio.get_running_loop(),
        ip_type=IPTypes.SQL_DATA,
        resource_exhausted_cooldown_period=0.5,
    ) as connector:
        connector._client = fake_client

        captured_on_resource_exhausted = None
        captured_on_success = None

        mock_sqldata_instance = MagicMock()

        async def mock_connect_tunnel(**kwargs):
            nonlocal captured_on_resource_exhausted, captured_on_success
            captured_on_resource_exhausted = kwargs.get("on_resource_exhausted")
            captured_on_success = kwargs.get("on_success")
            return 3307

        mock_sqldata_instance.connect_tunnel = AsyncMock(
            side_effect=mock_connect_tunnel
        )
        mock_sqldata_instance.close = AsyncMock()

        with (
            patch(
                "google.cloud.sql.connector.connector.SqlDataClient",
                return_value=mock_sqldata_instance,
            ),
            patch("google.cloud.sql.connector.asyncpg.connect", return_value=True),
        ):
            # 1. Connect and trigger on_resource_exhausted
            await connector.connect_async(
                connect_string,
                "asyncpg",
                user="test-user",
                db="test-db",
            )
            assert captured_on_resource_exhausted is not None
            assert captured_on_success is not None

            state = connector._sql_data_conn_state[connect_string]
            assert state.backoff_counter == 0
            assert state.cooldown_until is None

            # Trigger resource exhausted
            captured_on_resource_exhausted(Exception("resource exhausted"))
            assert state.backoff_counter == 1
            assert state.cooldown_until is not None
            assert state.cooldown_until > time.time()

            # Second connect attempt during cooldown fails with ResourceExhaustedError
            with pytest.raises(ResourceExhaustedError):
                await connector.connect_async(
                    connect_string,
                    "asyncpg",
                    user="test-user",
                    db="test-db",
                )

            # Reset via on_success
            captured_on_success()
            assert state.backoff_counter == 0
            assert state.cooldown_until is None
            assert state.last_err is None




