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

import pytest  # noqa F401 Needed to run the tests

from google.cloud.sql.connector.rate_limiter import (
    AsyncRateLimiter,
)


async def rate_limiter_in_loop(
    max_capacity: int, rate: float, loop: asyncio.AbstractEventLoop
) -> AsyncRateLimiter:
    """Helper function to create AsyncRateLimiter object inside given event loop."""
    limiter = AsyncRateLimiter(max_capacity=max_capacity, rate=rate, loop=loop)
    return limiter


@pytest.mark.asyncio
async def test_rate_limiter_throttles_requests(
    async_loop: asyncio.AbstractEventLoop,
) -> None:
    """Test to check whether rate limiter will throttle incoming requests."""
    counter = 0
    # allow 2 requests to go through every 5 seconds
    limiter_future = asyncio.run_coroutine_threadsafe(
        rate_limiter_in_loop(max_capacity=2, rate=1 / 5, loop=async_loop), async_loop
    )
    limiter = limiter_future.result()

    async def increment() -> None:
        await limiter.acquire()
        nonlocal counter
        counter += 1

    # create 10 tasks calling increment()
    tasks = [async_loop.create_task(increment()) for _ in range(10)]

    # wait 10 seconds and check tasks
    done, pending = asyncio.run_coroutine_threadsafe(
        asyncio.wait(tasks, timeout=11), async_loop
    ).result()

    # verify 4 tasks completed and 6 pending due to rate limiter
    assert counter == 4
    assert len(done) == 4
    assert len(pending) == 6

    # cleanup pending tasks
    for task in pending:
        task.cancel()


@pytest.mark.asyncio
async def test_rate_limiter_completes_all_tasks(
    async_loop: asyncio.AbstractEventLoop,
) -> None:
    """Test to check all requests will go through rate limiter successfully."""
    counter = 0
    # allow 1 request to go through per second
    limiter_future = asyncio.run_coroutine_threadsafe(
        rate_limiter_in_loop(max_capacity=1, rate=1, loop=async_loop), async_loop
    )
    limiter = limiter_future.result()

    async def increment() -> None:
        await limiter.acquire()
        nonlocal counter
        counter += 1

    # create 10 tasks calling increment()
    tasks = [async_loop.create_task(increment()) for _ in range(10)]

    done, pending = asyncio.run_coroutine_threadsafe(
        asyncio.wait(tasks, timeout=30), async_loop
    ).result()

    # verify all tasks done and none pending
    assert counter == 10
    assert len(done) == 10
    assert len(pending) == 0
