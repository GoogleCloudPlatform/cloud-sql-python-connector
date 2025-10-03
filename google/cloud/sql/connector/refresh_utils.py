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

from __future__ import annotations

import asyncio
import copy
import datetime
import logging
import random
from typing import Any, Callable

import aiohttp
from google.auth.credentials import Credentials
from google.auth.credentials import Scoped
import google.auth.transport.requests

logger = logging.getLogger(name=__name__)

# _refresh_buffer is the amount of time before a refresh's result expires
# that a new refresh operation begins.
_refresh_buffer: int = 4 * 60  # 4 minutes


def _seconds_until_refresh(
    expiration: datetime.datetime,
) -> int:
    """
    Calculates the duration to wait before starting the next refresh.

    Usually the duration will be half of the time until certificate
    expiration.

    Args:
        expiration (datetime.datetime): The expiration time of the certificate.

    Returns:
        int: Time in seconds to wait before performing next refresh.
    """

    duration = int(
        (expiration - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    )

    # if certificate duration is less than 1 hour
    if duration < 3600:
        # something is wrong with certificate, refresh now
        if duration < _refresh_buffer:
            return 0
        # otherwise wait until 4 minutes before expiration for next refresh
        return duration - _refresh_buffer

    return duration // 2


async def _is_valid(task: asyncio.Task) -> bool:
    try:
        metadata = await task
        # only valid if now is before the cert expires
        if datetime.datetime.now(datetime.timezone.utc) < metadata.expiration:
            return True
    except Exception:
        # supress any errors from task
        logger.debug("Current instance metadata is invalid.")
    return False


def _downscope_credentials(
    credentials: Credentials,
    scopes: list[str] = ["https://www.googleapis.com/auth/sqlservice.login"],
) -> Credentials:
    """Generate a down-scoped credential.

    Args:
        credentials (google.auth.credentials.Credentials):
            Credentials object used to generate down-scoped credentials.
        scopes (list[str]): List of Google scopes to
            include in down-scoped credentials object.

    Returns:
        google.auth.credentials.Credentials: Down-scoped credentials object.
    """
    # credentials sourced from a service account or metadata are children of
    # Scoped class and are capable of being re-scoped
    if isinstance(credentials, Scoped):
        scoped_creds = credentials.with_scopes(scopes=scopes)
    # authenticated user credentials can not be re-scoped
    else:
        # create shallow copy to not overwrite scopes on default credentials
        scoped_creds = copy.copy(credentials)
        # overwrite '_scopes' to down-scope user credentials
        # Cloud SDK reference: https://github.com/google-cloud-sdk-unofficial/google-cloud-sdk/blob/93920ccb6d2cce0fe6d1ce841e9e33410551d66b/lib/googlecloudsdk/command_lib/sql/generate_login_token_util.py#L116
        scoped_creds._scopes = scopes # type: ignore[attr-defined]
    # down-scoped credentials require refresh, are invalid after being re-scoped
    request = google.auth.transport.requests.Request()
    scoped_creds.refresh(request)
    return scoped_creds


def _exponential_backoff(attempt: int) -> float:
    """Calculates a duration to backoff in milliseconds based on the attempt i.

    The formula is:

    base * multi^(attempt + 1 + random)

    With base = 200ms and multi = 1.618, and random = [0.0, 1.0),
    the backoff values would fall between the following low and high ends:

    Attempt  Low (ms)  High (ms)

    0         324	     524
    1         524	     847
    2         847	    1371
    3        1371	    2218
    4        2218	    3588

    The theoretical worst case scenario would have a client wait 8.5s in total
    for an API request to complete (with the first four attempts failing, and
    the fifth succeeding).
    """
    base = 200
    multi = 1.618
    exp = attempt + 1 + random.random()
    return base * pow(multi, exp)


async def retry_50x(
    request_coro: Callable, *args: Any, **kwargs: Any
) -> aiohttp.ClientResponse:
    """Retry any 50x HTTP response up to X number of times."""
    max_retries = 5
    for i in range(max_retries):
        resp = await request_coro(*args, **kwargs)
        # backoff for any 50X errors
        if resp.status >= 500 and i < max_retries:
            # calculate backoff time
            backoff = _exponential_backoff(i)
            await asyncio.sleep(backoff / 1000)
        else:
            break
    return resp
