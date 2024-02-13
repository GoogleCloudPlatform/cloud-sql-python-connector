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
from typing import Optional


class AsyncRateLimiter(object):
    """
    An asyncio-compatible rate limiter which uses the Token Bucket algorithm
    (https://en.wikipedia.org/wiki/Token_bucket) to limit the number of function calls over a time interval using an event queue.

    :type max_capacity: int
    :param: max_capacity:
        The maximum capacity of tokens the bucket will store at any one time.
        Default: 1

    :type rate: float
    :param: rate:
        The number of tokens that should be added per second.

    :type loop: asyncio.AbstractEventLoop
    :param: loop:
        The event loop to use. If not provided, the default event loop will be used.


    """

    def __init__(
        self,
        max_capacity: int = 1,
        rate: float = 1 / 60,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.rate = rate
        self.max_capacity = max_capacity
        self._loop = loop or asyncio.get_event_loop()
        self._tokens: float = max_capacity
        self._last_token_update = self._loop.time()
        self._lock = asyncio.Lock()

    def _update_token_count(self) -> None:
        """
        Calculates how much time has passed since the last leak and removes the
        appropriate amount of events from the queue.
        Leaking is done lazily, meaning that if there is a large time gap between
        leaks, the next set of calls might be a burst if burst_size > 1
        """
        now = self._loop.time()
        time_elapsed = now - self._last_token_update
        new_tokens = time_elapsed * self.rate
        self._tokens = min(new_tokens + self._tokens, self.max_capacity)
        self._last_token_update = now

    async def _wait_for_next_token(self) -> None:
        """
        Wait until enough time has elapsed to add another token.
        """
        token_deficit = 1 - self._tokens
        if token_deficit > 0:
            wait_time = token_deficit / self.rate
            await asyncio.sleep(wait_time)

    async def acquire(self) -> None:
        """
        Waits for a token to become available, if necessary, then subtracts token and allows
        request to go through.
        """
        async with self._lock:
            self._update_token_count()
            if self._tokens < 1:
                await self._wait_for_next_token()
                self._update_token_count()
            self._tokens -= 1
