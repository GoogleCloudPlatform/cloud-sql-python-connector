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
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from typing import Any
import pytest  # noqa F401 Needed to run the tests
from google.cloud.sql.connector.instance_connection_manager import (
    InstanceConnectionManager,
)
from google.cloud.sql.connector.utils import generate_keys


@pytest.fixture
def icm(
    async_loop: asyncio.AbstractEventLoop, connect_string: str
) -> InstanceConnectionManager:
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)

    return icm


@pytest.fixture
def test_rate_limiter(async_loop: asyncio.AbstractEventLoop) -> AsyncRateLimiter:
    return AsyncRateLimiter(burst_size=1, interval=2, loop=async_loop)


class MockMetadata:
    def __init__(self, expiration: datetime.datetime) -> None:
        self.expiration = expiration


async def _get_metadata_success(*args: Any, **kwargs: Any) -> MockMetadata:
    return MockMetadata(datetime.datetime.now() + datetime.timedelta(minutes=10))


async def _get_metadata_error(*args: Any, **kwargs: Any) -> None:
    raise Exception("something went wrong...")


def test_InstanceConnectionManager_init(async_loop: asyncio.AbstractEventLoop) -> None:
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """

    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)
    project_result = icm._project
    region_result = icm._region
    instance_result = icm._instance

    assert (
        project_result == "test-project"
        and region_result == "test-region"
        and instance_result == "test-instance"
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
    setattr(icm, "_get_instance_data", _get_metadata_success)
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
    setattr(icm, "_get_instance_data", _get_metadata_success)
    icm._current = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)
    old_task = icm._current

    # stub _get_instance_data to throw an error, then await _perform_refresh
    setattr(icm, "_get_instance_data", _get_metadata_error)
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

    # stub _get_instance_data to throw an error
    setattr(icm, "_get_instance_data", _get_metadata_error)
    icm._current = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)

    # stub _get_instance_data to return a MockMetadata instance
    setattr(icm, "_get_instance_data", _get_metadata_success)
    new_task = asyncio.run_coroutine_threadsafe(
        icm._perform_refresh(), icm._loop
    ).result(timeout=10)

    assert icm._current == new_task
    assert isinstance(icm._current.result(), MockMetadata)
