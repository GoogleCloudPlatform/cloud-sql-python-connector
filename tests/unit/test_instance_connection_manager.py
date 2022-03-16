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
from concurrent.futures import CancelledError
from unittest.mock import patch
import datetime
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from typing import Any
import pytest  # noqa F401 Needed to run the tests
from google.auth.credentials import Credentials
from google.cloud.sql.connector.instance_connection_manager import (
    InstanceConnectionManager,
    CredentialsTypeError,
)
from google.cloud.sql.connector.utils import generate_keys


class BadRefresh(Exception):
    pass


class MockMetadata:
    def __init__(self, expiration: datetime.datetime) -> None:
        self.expiration = expiration


async def _get_metadata_success(*args: Any, **kwargs: Any) -> MockMetadata:
    return MockMetadata(datetime.datetime.now() + datetime.timedelta(minutes=10))


async def _get_metadata_expired(*args: Any, **kwargs: Any) -> MockMetadata:
    return MockMetadata(datetime.datetime.now() - datetime.timedelta(minutes=10))


async def _get_metadata_error(*args: Any, **kwargs: Any) -> None:
    raise BadRefresh("something went wrong...")


async def refresh(icm: InstanceConnectionManager, wait: bool = False) -> asyncio.Task:
    """
    Helper function to run schedule_refresh within background thread's event_loop
    """
    new_task = icm._schedule_refresh(0)

    # since we can't await in test itself we set flag to await in background thread for result
    if wait:
        await new_task

    return new_task


@pytest.fixture
@patch.object(InstanceConnectionManager, "_perform_refresh", _get_metadata_success)
def icm(
    fake_credentials: Credentials,
    async_loop: asyncio.AbstractEventLoop,
) -> InstanceConnectionManager:
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
        icm = InstanceConnectionManager(
            "my-project:my-region:my-instance", "pymysql", keys, async_loop
        )
        return icm


@pytest.fixture
def test_rate_limiter(async_loop: asyncio.AbstractEventLoop) -> AsyncRateLimiter:
    async def rate_limiter_in_loop(
        async_loop: asyncio.AbstractEventLoop,
    ) -> AsyncRateLimiter:
        return AsyncRateLimiter(max_capacity=1, rate=1 / 2, loop=async_loop)

    limiter_future = asyncio.run_coroutine_threadsafe(
        rate_limiter_in_loop(async_loop), async_loop
    )
    limiter = limiter_future.result()
    return limiter


def test_InstanceConnectionManager_init(
    fake_credentials: Credentials, async_loop: asyncio.AbstractEventLoop
) -> None:
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """

    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)
    project_result = icm._project
    region_result = icm._region
    instance_result = icm._instance
    # cleanup icm
    asyncio.run_coroutine_threadsafe(icm.close(), icm._loop).result(timeout=5)

    assert (
        project_result == "test-project"
        and region_result == "test-region"
        and instance_result == "test-instance"
    )


def test_InstanceConnectionManager_init_bad_credentials(
    async_loop: asyncio.AbstractEventLoop,
) -> None:
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    throws proper error for bad credentials arg type.
    """
    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    with pytest.raises(CredentialsTypeError):
        assert InstanceConnectionManager(
            connect_string, "pymysql", keys, async_loop, credentials=1
        )


@pytest.mark.asyncio
async def test_schedule_refresh_replaces_result(
    icm: InstanceConnectionManager, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _schedule_refresh replaces a valid result with another valid result
    """
    # allow more frequent refreshes for tests
    setattr(icm, "_refresh_rate_limiter", test_rate_limiter)

    # stub _perform_refresh to return a "valid" MockMetadata object
    setattr(icm, "_perform_refresh", _get_metadata_success)

    old_metadata = icm._current.result()

    # schedule refresh immediately and await it
    refresh_task = asyncio.run_coroutine_threadsafe(
        refresh(icm, wait=True), icm._loop
    ).result(timeout=5)
    refresh_metadata = refresh_task.result()

    # check that current metadata has been replaced with refresh metadata
    assert icm._current.result() == refresh_metadata
    assert old_metadata != icm._current.result()
    assert isinstance(icm._current.result(), MockMetadata)
    # cleanup icm
    asyncio.run_coroutine_threadsafe(icm.close(), icm._loop).result(timeout=5)


@pytest.mark.asyncio
async def test_schedule_refresh_wont_replace_valid_result_with_invalid(
    icm: InstanceConnectionManager, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh won't replace a valid _current
    value with an invalid one
    """
    # allow more frequent refreshes for tests
    setattr(icm, "_refresh_rate_limiter", test_rate_limiter)

    old_task = icm._current

    # stub _perform_refresh to throw an error
    setattr(icm, "_perform_refresh", _get_metadata_error)

    # schedule refresh immediately
    refresh_task = icm._schedule_refresh(0)

    # wait for invalid refresh to finish
    with pytest.raises(BadRefresh):
        asyncio.run_coroutine_threadsafe(
            asyncio.wait_for(refresh_task, timeout=5), icm._loop
        ).result(timeout=5)

    # check that invalid refresh did not replace valid current metadata
    assert icm._current == old_task
    assert isinstance(icm._current.result(), MockMetadata)
    # cleanup icm
    asyncio.run_coroutine_threadsafe(icm.close(), icm._loop).result(timeout=5)


@pytest.mark.asyncio
async def test_schedule_refresh_replaces_invalid_result(
    icm: InstanceConnectionManager, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh will replace an invalid refresh result with
    a valid one
    """
    # allow more frequent refreshes for tests
    setattr(icm, "_refresh_rate_limiter", test_rate_limiter)

    # stub _perform_refresh to throw an error
    setattr(icm, "_perform_refresh", _get_metadata_error)

    # set current to invalid data (error)
    icm._current = icm._schedule_refresh(0)

    # wait for invalid refresh to finish
    with pytest.raises(BadRefresh):
        assert asyncio.run_coroutine_threadsafe(
            asyncio.wait_for(icm._current, timeout=5), icm._loop
        ).result()

    # check that current is now invalid (error)
    with pytest.raises(BadRefresh):
        assert icm._current.result()

    # stub _perform_refresh to return a valid MockMetadata instance
    setattr(icm, "_perform_refresh", _get_metadata_success)

    # schedule refresh immediately and await it
    refresh_task = asyncio.run_coroutine_threadsafe(
        refresh(icm, wait=True), icm._loop
    ).result(timeout=5)
    refresh_metadata = refresh_task.result()

    # check that current is now valid MockMetadata
    assert icm._current.result() == refresh_metadata
    assert isinstance(icm._current.result(), MockMetadata)
    # cleanup icm
    asyncio.run_coroutine_threadsafe(icm.close(), icm._loop).result(timeout=5)


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

    # stub _perform_refresh to return a MockMetadata instance
    setattr(icm, "_perform_refresh", _get_metadata_success)

    # since the pending refresh isn't for another 55 min, the refresh_in_progress event
    # shouldn't be set
    pending_refresh = icm._next

    assert icm._refresh_in_progress.is_set() is False

    icm.force_refresh()

    # pending_refresh has to be awaited for it to raised as cancelled
    with pytest.raises(CancelledError):
        assert asyncio.run_coroutine_threadsafe(
            asyncio.wait_for(pending_refresh, timeout=5), icm._loop
        ).result(timeout=5)

    # verify pending_refresh has now been cancelled
    assert pending_refresh.cancelled() is True
    assert isinstance(icm._current.result(), MockMetadata)
    # cleanup icm
    asyncio.run_coroutine_threadsafe(icm.close(), icm._loop).result(timeout=5)


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
