""""
Copyright 2019 Google LLC

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
from unittest.mock import patch
import datetime
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from typing import Any, Dict
import pytest  # noqa F401 Needed to run the tests
from google.auth.credentials import Credentials
from google.cloud.sql.connector.instance_connection_manager import (
    InstanceConnectionManager,
    CredentialsTypeError,
)
from google.cloud.sql.connector.utils import generate_keys


class MockMetadata:
    def __init__(self, expiration: datetime.datetime) -> None:
        self.expiration = expiration


async def _get_instance_data_success(*args: Any, **kwargs: Any) -> MockMetadata:
    return MockMetadata(datetime.datetime.now() + datetime.timedelta(minutes=10))


async def _get_instance_data_error(*args: Any, **kwargs: Any) -> None:
    raise Exception("something went wrong...")

server_ca_cert = b"""
-----BEGIN CERTIFICATE-----
MIIDfzCCAmegAwIBAgIBADANBgkqhkiG9w0BAQsFADB3MS0wKwYDVQQuEyRmY2Yx
ZTM3MC04Y2EwLTRlMmItYjE4OC1lZTY4MDI0ODFjY2IxIzAhBgNVBAMTGkdvb2ds
ZSBDbG91ZCBTUUwgU2VydmVyIENBMRQwEgYDVQQKEwtHb29nbGUsIEluYzELMAkG
A1UEBhMCVVMwHhcNMjExMTAzMTczMjA5WhcNMzExMTAxMTczMzA5WjB3MS0wKwYD
VQQuEyRmY2YxZTM3MC04Y2EwLTRlMmItYjE4OC1lZTY4MDI0ODFjY2IxIzAhBgNV
BAMTGkdvb2dsZSBDbG91ZCBTUUwgU2VydmVyIENBMRQwEgYDVQQKEwtHb29nbGUs
IEluYzELMAkGA1UEBhMCVVMwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIB
AQCBH0PKs9heYhER0qfNeHt1NYTmMXiyX0M7ZXAaChAirptZRWFwHI5h/2C+EZ55
Ky7uMxXur1o3zot/jgQeD3gxAq6w2uDjvEkMd/jM8+uNasNAX78+UVzl7ehoHdad
9bs7nDRyc58nKhtMtm3e40cgN7dcPi7CfTScqzLHpWdW2TriR/UYmdpfGU3HY/4+
hCGNmmiVKvNEpxOpM9DoAKFK9d1rRBUUEfClM9F4vARxC0nmRkkU2nVsJef9GkOH
9ODcpzdB4YUj3uJuGlAlwWzm3J9vjerFXtJOiTI+z4IviWdbDlvwAvNBpPZQ/ELi
v9B6acmpvrqyU9or6rqv8zkdAgMBAAGjFjAUMBIGA1UdEwEB/wQIMAYBAf8CAQAw
DQYJKoZIhvcNAQELBQADggEBAGS+PtLmBhAEykDwcg+TkqhbaI/aj0jYOJ+9ncbd
iUjsKVqXVh7BgbBDg9mfIf/EyAOrOSe2FSmxhABsvA3EoRZYI1KMTRiMxcSimNMs
0NMOd62SUiZ5jPs/LYLecSJ48RZBb2nd3VOZQndiYopXs58sMKpwNlhzah5vEhf9
KbIzna0Pbd8ygwv23RMz9le+Gvr3hNtgE39PHd1her8786q+DYWKfcdo4r5EwQ1L
1z6R4QUEvkdWsL20qVetAiXswP/bj73LPa+f2600NRPfzG+mX4yQzwC7Kj+Uykgj
fnGYLhfBbJ5q8a+u89ojTxbzydmT0ZehatPgy9IunsLwwmE=
-----END CERTIFICATE-----
"""
async def _get_metadata_success(*args: Any, **kwargs: Any) -> Dict:
    return {
        "ip_addresses": {'PRIMARY': '0.0.0.0'},
        "server_ca_cert": server_ca_cert
    }

async def _get_ephemeral_success():
    return "-----BEGIN CERTIFICATE-----\nabc123\n-----END CERTIFICATE-----"


@pytest.fixture
@patch.object(
    InstanceConnectionManager, "_get_instance_data", _get_instance_data_success
)
def icm(
    fake_credentials: Credentials,
    event_loop: asyncio.AbstractEventLoop,
) -> InstanceConnectionManager:
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        keys = asyncio.run_coroutine_threadsafe(generate_keys(), event_loop)
        icm = InstanceConnectionManager(
            "my-project:my-region:my-instance", "pymysql", keys, event_loop
        )
        return icm


@pytest.fixture
def test_rate_limiter(event_loop: asyncio.AbstractEventLoop) -> AsyncRateLimiter:
    async def rate_limiter_in_loop(
        event_loop: asyncio.AbstractEventLoop,
    ) -> AsyncRateLimiter:
        return AsyncRateLimiter(max_capacity=1, rate=1 / 2, loop=event_loop)

    limiter_future = asyncio.run_coroutine_threadsafe(
        rate_limiter_in_loop(event_loop), event_loop
    )
    limiter = limiter_future.result()
    return limiter


def test_InstanceConnectionManager_init(
    fake_credentials: Credentials, event_loop: asyncio.AbstractEventLoop
) -> None:
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """

    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), event_loop)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        icm = InstanceConnectionManager(connect_string, "pymysql", keys, event_loop)
    project_result = icm._project
    region_result = icm._region
    instance_result = icm._instance

    assert (
        project_result == "test-project"
        and region_result == "test-region"
        and instance_result == "test-instance"
    )


def test_InstanceConnectionManager_init_bad_credentials(
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    throws proper error for bad credentials arg type.
    """
    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), event_loop)
    with pytest.raises(CredentialsTypeError):
        assert InstanceConnectionManager(
            connect_string, "pymysql", keys, event_loop, credentials=1
        )


@pytest.mark.asyncio
async def test_perform_refresh_replaces_result(
    icm: InstanceConnectionManager, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh replaces a valid result with another valid result
    """
    # allow more frequent refreshes for tests
    setattr(icm, "_refresh_rate_limiter", test_rate_limiter)

    # stub _get_instance_data to return a "valid" MockMetadata object
    setattr(icm, "_get_instance_data", _get_instance_data_success)
    new_task = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)

    assert icm._current == new_task
    assert isinstance(icm._current.result(), MockMetadata)


@pytest.mark.asyncio
async def test_perform_refresh_wont_replace_valid_result_with_invalid(
    icm: InstanceConnectionManager, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh won't replace a valid _current
    value with an invalid one
    """
    # allow more frequent refreshes for tests
    setattr(icm, "_refresh_rate_limiter", test_rate_limiter)

    # stub _get_instance_data to return a "valid" MockMetadata object
    setattr(icm, "_get_instance_data", _get_instance_data_success)
    icm._current = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)
    old_task = icm._current

    # stub _get_instance_data to throw an error, then await _perform_refresh
    setattr(icm, "_get_instance_data", _get_instance_data_error)
    asyncio.run_coroutine_threadsafe(icm._perform_refresh(), icm._loop).result(
        timeout=10
    )

    assert icm._current == old_task
    assert isinstance(icm._current.result(), MockMetadata)


@pytest.mark.asyncio
async def test_perform_refresh_replaces_invalid_result(
    icm: InstanceConnectionManager, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh will replace an invalid refresh result with
    a valid one
    """
    # allow more frequent refreshes for tests
    setattr(icm, "_refresh_rate_limiter", test_rate_limiter)

    # set current to valid MockMetadata instance
    setattr(icm, "_get_instance_data", _get_instance_data_success)
    icm._current = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)

    # stub _get_instance_data to throw an error
    setattr(icm, "_get_instance_data", _get_instance_data_error)
    icm._current = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)

    # stub _get_instance_data to return a MockMetadata instance
    setattr(icm, "_get_instance_data", _get_instance_data_success)
    new_task = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)

    assert icm._current == new_task
    assert isinstance(icm._current.result(), MockMetadata)


@pytest.mark.asyncio
async def test_force_refresh_cancels_pending_refresh(
    icm: InstanceConnectionManager,
    test_rate_limiter: AsyncRateLimiter,
) -> None:
    """
    Test that force_refresh cancels pending task if refresh_in_progress event is not set.
    """
    # allow more frequent refreshes for tests
    setattr(icm, "_refresh_rate_limiter", test_rate_limiter)

    # stub _get_instance_data to return a MockMetadata instance
    setattr(icm, "_get_instance_data", _get_instance_data_success)

    # set _current to MockMetadata
    icm._current = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)

    # since the pending refresh isn't for another 55 min, the refresh_in_progress event
    # shouldn't be set
    pending_refresh = icm._next
    assert icm._refresh_in_progress.is_set() is False

    icm.force_refresh()

    assert pending_refresh.cancelled() is True
    assert isinstance(icm._current.result(), MockMetadata)


@pytest.mark.asyncio
@patch("google.cloud.sql.connector.instance_connection_manager._get_ephemeral")
@patch("google.cloud.sql.connector.instance_connection_manager._get_metadata")
async def test_get_instance_data(mock_metadata, mock_ephemeral, icm: InstanceConnectionManager):
    """
    Test that _get_instance_data returns valid InstanceMetadata object.
    """
    mock_metadata.return_value = _get_metadata_success()
    mock_ephemeral.return_value = _get_ephemeral_success()
    instance_metadata = await icm._get_instance_data()


def test_auth_init_with_credentials_object(
    icm: InstanceConnectionManager, fake_credentials: Credentials
) -> None:
    """
    Test that InstanceConnectionManager's _auth_init initializes _credentials
    when passed a google.auth.credentials.Credentials object.
    """
    setattr(icm, "_credentials", None)
    with patch(
        "google.cloud.sql.connector.instance_connection_manager.with_scopes_if_required"
    ) as mock_auth:
        mock_auth.return_value = fake_credentials
        icm._auth_init(credentials=fake_credentials)
        assert isinstance(icm._credentials, Credentials)
        mock_auth.assert_called_once()


def test_auth_init_with_default_credentials(
    icm: InstanceConnectionManager, fake_credentials: Credentials
) -> None:
    """
    Test that InstanceConnectionManager's _auth_init initializes _credentials
    with application default credentials when credentials are not specified.
    """
    setattr(icm, "_credentials", None)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        icm._auth_init(credentials=None)
        assert isinstance(icm._credentials, Credentials)
        mock_auth.assert_called_once()
