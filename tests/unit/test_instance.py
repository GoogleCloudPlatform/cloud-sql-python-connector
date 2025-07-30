"""
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
import datetime

from mock import patch
import mocks
import pytest  # noqa F401 Needed to run the tests

from google.cloud.sql.connector import IPTypes
from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import AutoIAMAuthNotSupported
from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError
from google.cloud.sql.connector.instance import RefreshAheadCache
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.cloud.sql.connector.refresh_utils import _is_valid
from google.cloud.sql.connector.utils import generate_keys


@pytest.fixture
def test_rate_limiter() -> AsyncRateLimiter:
    return AsyncRateLimiter(max_capacity=1, rate=1 / 2)


@pytest.mark.asyncio
async def test_Instance_init(
    cache: RefreshAheadCache,
) -> None:
    """
    Test to check whether the __init__ method of RefreshAheadCache
    can tell if the connection string that's passed in is formatted correctly.
    """
    assert (
        cache._conn_name.project == "test-project"
        and cache._conn_name.region == "test-region"
        and cache._conn_name.instance_name == "test-instance"
    )
    assert cache._enable_iam_auth is False


@pytest.mark.asyncio
async def test_schedule_refresh_replaces_result(cache: RefreshAheadCache) -> None:
    """
    Test to check whether _schedule_refresh replaces a valid result with another valid result
    """

    # check current refresh is valid
    assert await _is_valid(cache._current) is True
    current_refresh = cache._current
    # schedule new refresh
    await cache._schedule_refresh(0)
    new_refresh = cache._current
    # verify current has been replaced with new refresh
    assert current_refresh != new_refresh
    # check new refresh is valid
    assert await _is_valid(new_refresh) is True


@pytest.mark.asyncio
async def test_schedule_refresh_wont_replace_valid_result_with_invalid(
    cache: RefreshAheadCache,
) -> None:
    """
    Test to check whether _perform_refresh won't replace a valid _current
    value with an invalid one
    """
    # check current refresh is valid
    assert await _is_valid(cache._current) is True
    current_refresh = cache._current
    # set certificate to be expired
    cache._client.instance.cert_expiration = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(minutes=10)
    # cert not_valid_before has to be before expiry
    cache._client.instance.cert_before = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(minutes=20)
    # schedule new refresh
    new_refresh = cache._schedule_refresh(0)
    # check new refresh is invalid
    assert await _is_valid(new_refresh) is False
    # check current was not replaced
    assert await current_refresh == await cache._current


@pytest.mark.asyncio
async def test_schedule_refresh_replaces_invalid_result(
    cache: RefreshAheadCache,
    test_rate_limiter: AsyncRateLimiter,
) -> None:
    """
    Test to check whether _perform_refresh will replace an invalid refresh result with
    a valid one
    """
    # allow more frequent refreshes for tests
    setattr(cache, "_refresh_rate_limiter", test_rate_limiter)
    # set certificate to be expired
    cache._client.instance.cert_expiration = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(minutes=10)
    # cert not_valid_before has to be before expiry
    cache._client.instance.cert_before = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(minutes=20)
    # set current to invalid (expired)
    cache._current = cache._schedule_refresh(0)

    # check current is invalid
    assert await _is_valid(cache._current) is False

    # set certificate to valid
    cache._client.instance.cert_before = datetime.datetime.now(datetime.timezone.utc)
    cache._client.instance.cert_expiration = datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(hours=1)

    # schedule refresh immediately and await it
    refresh_task = cache._schedule_refresh(0)
    await refresh_task

    # check that current is now valid
    assert await _is_valid(cache._current) is True


@pytest.mark.asyncio
async def test_force_refresh_cancels_pending_refresh(
    cache: RefreshAheadCache,
    test_rate_limiter: AsyncRateLimiter,
) -> None:
    """
    Test that force_refresh cancels pending task if lock is not acquired.
    """
    # allow more frequent refreshes for tests
    setattr(cache, "_refresh_rate_limiter", test_rate_limiter)
    # make sure initial refresh is finished
    await cache._current
    # since the pending refresh isn't for another 55 min, the lock should not
    # be acquired
    pending_refresh = cache._next
    assert cache._lock.locked() is False

    await cache.force_refresh()

    # pending_refresh has to be awaited for it to raised as cancelled
    with pytest.raises(asyncio.CancelledError):
        assert await pending_refresh

    # verify pending_refresh has now been cancelled
    assert pending_refresh.cancelled() is True
    assert isinstance(await cache._current, ConnectionInfo)


@pytest.mark.asyncio
async def test_RefreshAheadCache_close(cache: RefreshAheadCache) -> None:
    """
    Test that RefreshAheadCache's close method
    cancels tasks and closes ClientSession.
    """
    # make sure current metadata task is done
    await cache._current
    assert cache._current.cancelled() is False
    assert cache._next.cancelled() is False
    # run close() to cancel tasks and close ClientSession
    await cache.close()
    # verify tasks are cancelled and ClientSession is closed
    assert (cache._current.done() or cache._current.cancelled()) is True
    assert cache._next.cancelled() is True


@pytest.mark.asyncio
async def test_perform_refresh(
    cache: RefreshAheadCache,
) -> None:
    """
    Test that _perform_refresh returns valid ConnectionInfo object.
    """
    instance_metadata = await cache._perform_refresh()
    # verify instance metadata object is returned
    assert isinstance(instance_metadata, ConnectionInfo)
    # verify instance metadata expiration
    assert (
        cache._client.instance.cert_expiration.replace(microsecond=0)
        == instance_metadata.expiration
    )


@pytest.mark.asyncio
async def test_perform_refresh_expiration(
    cache: RefreshAheadCache,
) -> None:
    """
    Test that _perform_refresh returns ConnectionInfo with proper expiration.

    If credentials expiration is less than cert expiration,
    credentials expiration should be used.
    """
    # set credentials expiration to 1 minute from now
    expiration = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=1
    )
    credentials = mocks.FakeCredentials(token="my-token", expiry=expiration)
    setattr(cache, "_enable_iam_auth", True)
    # set downscoped credential to mock
    with patch("google.cloud.sql.connector.client._downscope_credentials") as mock_auth:
        mock_auth.return_value = credentials
        instance_metadata = await cache._perform_refresh()
    mock_auth.assert_called_once()
    # verify instance metadata object is returned
    assert isinstance(instance_metadata, ConnectionInfo)
    # verify instance metadata uses credentials expiration
    assert expiration == instance_metadata.expiration


@pytest.mark.asyncio
async def test_connect_info(
    cache: RefreshAheadCache,
) -> None:
    """
    Test that connect_info returns current metadata and preferred IP.
    """
    conn_info = await cache.connect_info()
    ip_addr = conn_info.get_preferred_ip(IPTypes.PUBLIC)

    # verify connection info and ip address
    assert isinstance(conn_info, ConnectionInfo)
    assert ip_addr == "127.0.0.1"


@pytest.mark.asyncio
async def test_get_preferred_ip_CloudSQLIPTypeError(cache: RefreshAheadCache) -> None:
    """
    Test that get_preferred_ip throws proper CloudSQLIPTypeError
    when missing Public or Private IP addresses.
    """
    instance_metadata: ConnectionInfo = await cache._current
    instance_metadata.ip_addrs = {"PRIVATE": "1.1.1.1"}
    # test error when Public IP is missing
    with pytest.raises(CloudSQLIPTypeError):
        instance_metadata.get_preferred_ip(IPTypes.PUBLIC)

    # test error when Private IP is missing
    instance_metadata.ip_addrs = {"PRIMARY": "0.0.0.0"}
    with pytest.raises(CloudSQLIPTypeError):
        instance_metadata.get_preferred_ip(IPTypes.PRIVATE)

    # test error when PSC is missing
    with pytest.raises(CloudSQLIPTypeError):
        instance_metadata.get_preferred_ip(IPTypes.PSC)


@pytest.mark.asyncio
async def test_AutoIAMAuthNotSupportedError(fake_client: CloudSQLClient) -> None:
    """
    Test that AutoIAMAuthNotSupported exception is raised
    for SQL Server instances.
    """
    # generate client key pair
    keys = asyncio.create_task(generate_keys())
    cache = RefreshAheadCache(
        ConnectionName("test-project", "test-region", "sqlserver-instance"),
        client=fake_client,
        keys=keys,
        enable_iam_auth=True,
    )
    with pytest.raises(AutoIAMAuthNotSupported):
        await cache._current


async def test_ConnectionInfo_caches_sslcontext() -> None:
    info = ConnectionInfo(
        "", "cert", "cert", "key".encode(), {}, "POSTGRES", datetime.datetime.now()
    )
    # context should default to None
    assert info.context is None
    # cache a 'context'
    info.context = "context"
    # calling create_ssl_context should no-op with an existing 'context'
    await info.create_ssl_context()
    assert info.context == "context"
