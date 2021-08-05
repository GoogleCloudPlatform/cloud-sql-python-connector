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
    An asyncio-compatible rate limiter which uses the Leaky Bucket algorithm
    (https://en.wikipedia.org/wiki/Leaky_bucket) to limit the number of function calls over a time interval using an event queue.

    :type burst_size: int
    :param: burst_size:
        The max number of function calls that can occur at the same time
        Default: 1

    :type interval: int
    :param: interval:
        The period of time over which a number of calls equal to burst_size are allowed to complete. Default: 60s

    :type queue_size: int
    :param: interval:
        The number of tasks that are allowed to be queued if rate limiter cannot be acquired. If exceeded, a QueueFull error will be thrown. A queue size of zero means the queue length has no upper bound. If setting queue size to a value greater than zero, queue_size must be greater than or equal to burst_size
        Default: 0

    :type loop: asyncio.AbstractEventLoop
    :param: loop:
        The event loop to use. If not provided, the default event loop will be used.


    """

    def __init__(
        self,
        burst_size: int = 1,
        interval: float = 60,
        queue_size: int = 0,
        loop: asyncio.AbstractEventLoop = None,
    ) -> None:
        self.interval = interval
        self.burst_size = burst_size
        self._loop = loop or asyncio.get_event_loop()
        self._last_leak = time.time()
        self._queue: asyncio.Queue = asyncio.Queue(queue_size, loop=self._loop)

    def _leak(self) -> None:
        """
        Calculates how much time has passed since the last leak and removes the
        appropriate amount of events from the queue.
        Leaking is done lazily, meaning that if there is a large time gap between
        leaks, the next set of calls might be a burst if burst_size > 1
        """
        time_elapsed = time.time() - self._last_leak
        leak_amount = math.floor(time_elapsed * self.burst_size / self.interval)
        # don't allow more than burst_size to leak at once
        leak_amount = min(leak_amount, self.burst_size)
        if leak_amount > 0:
            self._last_leak = time.time()
        for _ in range(leak_amount):
            if not self._queue.empty():
                event = self._queue.get_nowait()
                event.set()
                self._queue.task_done()

    def _release_from_queue(self, waiter_task: asyncio.Task) -> bool:
        """
        Releases tasks out of the queue if enough time has elapsed.
        and returns whether the task has completed.
        """
        self._leak()
        return waiter_task.done()

    async def acquire(self) -> None:
        """
        Adds an event to the queue and creates a waiter task to wait
        for the event's turn in the queue.
        """
        event = asyncio.Event()
        self._queue.put_nowait(event)
        waiter_task = self._loop.create_task(event.wait())
        while not self._release_from_queue(waiter_task):
            try:
                # await until enough time has passed that another event is 
                # released from the queue. If an event is released before this
                #  time, the waiter_task will complete and we will break out of the loop.
                await asyncio.wait_for(
                    asyncio.shield(waiter_task), timeout=self.interval / self.burst_size
                )
            except asyncio.TimeoutError:
                # allow for another call to self._release_from_queue() which will remove
                #  and set events from the queue
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
