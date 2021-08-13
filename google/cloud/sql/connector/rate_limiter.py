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
import math
import time
from typing import Optional, Type
from types import TracebackType


class AsyncRateLimiter(object):
    """
    An asyncio-compatible rate limiter which uses the Token Bucket algorithm
    (https://en.wikipedia.org/wiki/Token_bucket) to limit the number of function calls over a time interval using an event queue.

    :type burst_size: int
    :param: burst_size:
        the maximum capacity of the bucket will store at any one time.
        Default: 1

    :type interval: int
    :param: interval:
        The period of time over which a number of calls equal to burst_size are allowed to complete. Default: 60s

    :type loop: asyncio.AbstractEventLoop
    :param: loop:
        The event loop to use. If not provided, the default event loop will be used.


    """

    def __init__(
        self,
        burst_size: int = 1,
        interval: float = 60,
        loop: asyncio.AbstractEventLoop = None,
    ) -> None:
        self.interval = interval
        self.burst_size = burst_size
        self._loop = loop or asyncio.get_event_loop()
        self._tokens = asyncio.BoundedSemaphore(burst_size, loop=self._loop)
        self._last_token_update = time.time()

    def _add_tokens(self) -> None:
        """
        Calculates how much time has passed since the last leak and removes the
        appropriate amount of events from the queue.
        Leaking is done lazily, meaning that if there is a large time gap between
        leaks, the next set of calls might be a burst if burst_size > 1
        """
        time_elapsed = time.time() - self._last_token_update
        amount = math.floor(time_elapsed * self.burst_size / self.interval)
        # don't allow more tokens than burst_size to be added at once
        amount = min(amount, self.burst_size)
        if amount > 0:
            self._last_token_update = time.time()
        for _ in range(amount):
            try:
                self._tokens.release()
            except ValueError:
                # we want to keep adding tokens until the semaphore reaches its upper bound
                break

    def _token_acquired(self, waiter_task: asyncio.Task) -> bool:
        """
        Releases tasks out of the queue if enough time has elapsed.
        """
        self._add_tokens()
        return waiter_task.done()

    async def acquire(self) -> None:
        """
        Adds an event to the queue and creates a waiter task to wait
        for the event's turn in the queue.
        """
        waiter_task = self._loop.create_task(self._tokens.acquire())
        while not self._token_acquired(waiter_task):
            try:
                # await until enough time has passed that another event is released from the queue. If an event is released before this time, the waiter_task will complete and we will break out of the loop.
                await asyncio.wait_for(
                    asyncio.shield(waiter_task), timeout=self.interval / self.burst_size
                )
            except asyncio.TimeoutError:
                # allow for another call to self._release_from_queue() which will remove and set events from the queue
                pass

    async def __aenter__(self) -> None:
        await self.acquire()
        return None

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        return None
