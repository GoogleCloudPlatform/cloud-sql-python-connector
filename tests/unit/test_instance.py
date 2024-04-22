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
import datetime
from typing import Tuple

from aiohttp import ClientResponseError
from aiohttp import RequestInfo
from aioresponses import aioresponses
from google.auth.credentials import Credentials
from mock import patch
import mocks
import pytest  # noqa F401 Needed to run the tests

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.exceptions import AutoIAMAuthNotSupported
from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError
from google.cloud.sql.connector.instance import _parse_instance_connection_name
from google.cloud.sql.connector.instance import ConnectionInfo
from google.cloud.sql.connector.instance import IPTypes
from google.cloud.sql.connector.instance import RefreshAheadCache
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.cloud.sql.connector.utils import generate_keys


@pytest.fixture
def test_rate_limiter() -> AsyncRateLimiter:
    return AsyncRateLimiter(max_capacity=1, rate=1 / 2)


@pytest.mark.parametrize(
    "connection_name, expected",
    [
        ("project:region:instance", ("project", "region", "instance")),
        (
            "domain-prefix:project:region:instance",
            ("domain-prefix:project", "region", "instance"),
        ),
    ],
)
def test_parse_instance_connection_name(
    connection_name: str, expected: Tuple[str, str, str]
) -> None:
    """
    Test that _parse_instance_connection_name works correctly on
    normal instance connection names and domain-scoped projects.
    """
    assert expected == _parse_instance_connection_name(connection_name)


def test_parse_instance_connection_name_bad_conn_name() -> None:
    """
    Tests that ValueError is thrown for bad instance connection names.
    """
    with pytest.raises(ValueError):
        _parse_instance_connection_name("project:instance")  # missing region


@pytest.mark.asyncio
async def test_Instance_init(
    cache: RefreshAheadCache,
) -> None:
    """
    Test to check whether the __init__ method of RefreshAheadCache
    can tell if the connection string that's passed in is formatted correctly.
    """
    assert (
        cache._project == "test-project"
        and cache._region == "test-region"
        and cache._instance == "test-instance"
    )
    assert cache._enable_iam_auth is False


@pytest.mark.asyncio
async def test_schedule_refresh_replaces_result(
    cache: RefreshAheadCache, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _schedule_refresh replaces a valid result with another valid result
    """
    # allow more frequent refreshes for tests
    setattr(cache, "_refresh_rate_limiter", test_rate_limiter)

    # stub _perform_refresh to return a "valid" MockMetadata object
    setattr(cache, "_perform_refresh", mocks.instance_metadata_success)

    old_metadata = await cache._current

    # schedule refresh immediately and await it
    refresh_task = cache._schedule_refresh(0)
    refresh_metadata = await refresh_task

    # check that current metadata has been replaced with refresh metadata
    assert cache._current.result() == refresh_metadata
    assert old_metadata != cache._current.result()
    assert isinstance(cache._current.result(), mocks.MockMetadata)
    # cleanup cache
    await cache.close()


@pytest.mark.asyncio
async def test_schedule_refresh_wont_replace_valid_result_with_invalid(
    cache: RefreshAheadCache, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh won't replace a valid _current
    value with an invalid one
    """
    # allow more frequent refreshes for tests
    setattr(cache, "_refresh_rate_limiter", test_rate_limiter)

    await cache._current
    old_task = cache._current

    # stub _perform_refresh to throw an error
    setattr(cache, "_perform_refresh", mocks.instance_metadata_error)

    # schedule refresh immediately
    refresh_task = cache._schedule_refresh(0)

    # wait for invalid refresh to finish
    with pytest.raises(mocks.BadRefresh):
        assert await refresh_task

    # check that invalid refresh did not replace valid current metadata
    assert cache._current == old_task
    assert isinstance(await cache._current, ConnectionInfo)


@pytest.mark.asyncio
async def test_schedule_refresh_replaces_invalid_result(
    cache: RefreshAheadCache, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh will replace an invalid refresh result with
    a valid one
    """
    # allow more frequent refreshes for tests
    setattr(cache, "_refresh_rate_limiter", test_rate_limiter)

    # stub _perform_refresh to throw an error
    setattr(cache, "_perform_refresh", mocks.instance_metadata_error)

    # set current to invalid data (error)
    cache._current = cache._schedule_refresh(0)

    # check that current is now invalid (error)
    with pytest.raises(mocks.BadRefresh):
        assert await cache._current

    # stub _perform_refresh to return a valid MockMetadata instance
    setattr(cache, "_perform_refresh", mocks.instance_metadata_success)

    # schedule refresh immediately and await it
    refresh_task = cache._schedule_refresh(0)
    refresh_metadata = await refresh_task

    # check that current is now valid MockMetadata
    assert cache._current.result() == refresh_metadata
    assert isinstance(cache._current.result(), mocks.MockMetadata)


@pytest.mark.asyncio
async def test_force_refresh_cancels_pending_refresh(
    cache: RefreshAheadCache,
    test_rate_limiter: AsyncRateLimiter,
) -> None:
    """
    Test that force_refresh cancels pending task if refresh_in_progress event is not set.
    """
    # allow more frequent refreshes for tests
    setattr(cache, "_refresh_rate_limiter", test_rate_limiter)
    # make sure initial refresh is finished
    await cache._current
    # since the pending refresh isn't for another 55 min, the refresh_in_progress event
    # shouldn't be set
    pending_refresh = cache._next
    assert cache._refresh_in_progress.is_set() is False

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
    fake_instance: mocks.FakeCSQLInstance,
) -> None:
    """
    Test that _perform_refresh returns valid ConnectionInfo object.
    """
    instance_metadata = await cache._perform_refresh()

    # verify instance metadata object is returned
    assert isinstance(instance_metadata, ConnectionInfo)
    # verify instance metadata expiration
    assert fake_instance.server_cert.not_valid_after_utc == instance_metadata.expiration


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
    instance_metadata, ip_addr = await cache.connect_info(IPTypes.PUBLIC)

    # verify metadata and ip address
    assert isinstance(instance_metadata, ConnectionInfo)
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
async def test_ClientResponseError(
    fake_credentials: Credentials,
) -> None:
    """
    Test that detailed error message is applied to ClientResponseError.
    """
    # mock Cloud SQL Admin API calls with exceptions
    keys = asyncio.create_task(generate_keys())
    client = CloudSQLClient(
        sqladmin_api_endpoint="https://sqladmin.googleapis.com",
        quota_project=None,
        credentials=fake_credentials,
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance/connectSettings"
    post_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance:generateEphemeralCert"
    with aioresponses() as mocked:
        mocked.get(
            get_url,
            status=403,
            exception=ClientResponseError(
                RequestInfo(get_url, "GET", headers=[]), history=[], status=403  # type: ignore
            ),
            repeat=True,
        )
        mocked.post(
            post_url,
            status=403,
            exception=ClientResponseError(
                RequestInfo(post_url, "POST", headers=[]), history=[], status=403  # type: ignore
            ),
            repeat=True,
        )
        cache = RefreshAheadCache(
            "my-project:my-region:my-instance",
            client,
            keys,
        )
        try:
            await cache._current
        except ClientResponseError as e:
            assert e.status == 403
            assert (
                e.message == "Forbidden: Authenticated IAM principal does not "
                "seeem authorized to make API request. Verify "
                "'Cloud SQL Admin API' is enabled within your GCP project and "
                "'Cloud SQL Client' role has been granted to IAM principal."
            )
        finally:
            await cache.close()
            await client.close()


@pytest.mark.asyncio
async def test_AutoIAMAuthNotSupportedError(fake_client: CloudSQLClient) -> None:
    """
    Test that AutoIAMAuthNotSupported exception is raised
    for SQL Server instances.
    """
    # generate client key pair
    keys = asyncio.create_task(generate_keys())
    cache = RefreshAheadCache(
        "test-project:test-region:sqlserver-instance",
        client=fake_client,
        keys=keys,
        enable_iam_auth=True,
    )
    with pytest.raises(AutoIAMAuthNotSupported):
        await cache._current
