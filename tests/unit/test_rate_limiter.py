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


@pytest.mark.asyncio
async def test_rate_limiter_throttles_requests() -> None:
    counter = 0
    # allow 2 requests to go through every 5 seconds
    limiter = AsyncRateLimiter(burst_size=2, interval=10)

    async def increment() -> None:
        async with limiter:
            nonlocal counter
            counter += 1

    tasks = [increment() for _ in range(10)]

    done, pending = await asyncio.wait(tasks, timeout=11)

    assert counter == 3
    assert len(done) == 3
    assert len(pending) == 7


@pytest.mark.asyncio
async def test_rate_limiter_rejects_if_queue_full() -> None:
    counter = 0
    # allow 1 request to go through per second
    limiter = AsyncRateLimiter(burst_size=1, interval=1, queue_size=6)

    async def increment() -> None:
        async with limiter:
            nonlocal counter
            counter += 1

    tasks = [increment() for _ in range(10)]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    errors = [r for r in results if isinstance(r, asyncio.queues.QueueFull)]

    assert counter == 7 # one task completes immediately and the rest are queued
    assert len(errors) == 3


@pytest.mark.asyncio
async def test_rate_limiter_completes_all_tasks_in_queue() -> None:
    counter = 0
    # allow 1 request to go through per second
    limiter = AsyncRateLimiter(burst_size=1, interval=1, queue_size=10)

    async def increment() -> None:
        async with limiter:
            nonlocal counter
            counter += 1

    tasks = [increment() for _ in range(10)]

    done, pending = await asyncio.wait(tasks, timeout=30)

    assert counter == 10
    assert len(done) == 10
    assert len(pending) == 0
