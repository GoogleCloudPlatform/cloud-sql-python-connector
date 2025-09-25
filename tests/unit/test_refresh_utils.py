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
import datetime

from conftest import SCOPES  # type: ignore
import google.auth
from google.auth.credentials import Credentials
from google.auth.credentials import TokenState
import google.oauth2.credentials
from mock import Mock
from mock import patch
import pytest  # noqa F401 Needed to run the tests

from google.cloud.sql.connector.refresh_utils import _downscope_credentials
from google.cloud.sql.connector.refresh_utils import _exponential_backoff
from google.cloud.sql.connector.refresh_utils import _is_valid
from google.cloud.sql.connector.refresh_utils import _seconds_until_refresh
from google.cloud.sql.connector.refresh_utils import retry_50x


@pytest.fixture
def credentials() -> Credentials:
    credentials = Mock(spec=Credentials)
    credentials.token_state = TokenState.FRESH
    credentials.token = "12345"
    return credentials


class FakeConnectionInfo:
    def __init__(self, expiration: datetime.datetime) -> None:
        self.expiration = expiration


async def set_expiration(expiration: datetime.datetime) -> FakeConnectionInfo:
    return FakeConnectionInfo(expiration)


@pytest.mark.asyncio
async def test_is_valid_with_valid_metadata() -> None:
    """
    Test to check that valid metadata with expiration in future returns True.
    """

    # task that returns class with expiration 10 mins in future
    task = asyncio.create_task(
        set_expiration(
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=10)
        )
    )
    assert await _is_valid(task)


@pytest.mark.asyncio
async def test_is_valid_with_expired_metadata() -> None:
    """
    Test to check that invalid metadata with expiration in past returns False.
    """
    # task that returns class with expiration 10 mins in past
    task = asyncio.create_task(
        set_expiration(
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=10)
        )
    )
    assert not await _is_valid(task)


def test_downscope_credentials_user() -> None:
    """
    Test _downscope_credentials with google.oauth2.credentials.Credentials
    which mimics an authenticated user.
    """
    creds = google.oauth2.credentials.Credentials("token", scopes=SCOPES)
    # override actual refresh URI
    with patch.object(
        google.oauth2.credentials.Credentials, "refresh", lambda *args: None
    ):
        credentials = _downscope_credentials(creds)
    # verify default credential scopes have not been altered
    assert creds.scopes == SCOPES
    # verify downscoped credentials have new scope
    assert credentials.scopes == ["https://www.googleapis.com/auth/sqlservice.login"]
    assert credentials != creds


def test_seconds_until_refresh_over_1_hour() -> None:
    """
    Test _seconds_until_refresh returns proper time in seconds.

    If expiration is over 1 hour, should return duration/2.
    """
    # using pytest.approx since sometimes can be off by a second
    assert (
        pytest.approx(
            _seconds_until_refresh(
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=62)
            ),
            1,
        )
        == 31 * 60
    )


def test_seconds_until_refresh_under_1_hour_over_4_mins() -> None:
    """
    Test _seconds_until_refresh returns proper time in seconds.

    If expiration is under 1 hour and over 4 minutes,
    should return duration-refresh_buffer (refresh_buffer = 4 minutes).
    """
    # using pytest.approx since sometimes can be off by a second
    assert (
        pytest.approx(
            _seconds_until_refresh(
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=5)
            ),
            1,
        )
        == 60
    )


def test_seconds_until_refresh_under_4_mins() -> None:
    """
    Test _seconds_until_refresh returns proper time in seconds.

    If expiration is under 4 minutes, should return 0.
    """
    assert (
        _seconds_until_refresh(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=3)
        )
        == 0
    )


@pytest.mark.parametrize(
    "attempt, low, high",
    [
        (0, 324, 524),
        (1, 524, 847),
        (2, 847, 1371),
        (3, 1371, 2218),
        (4, 2218, 3588),
    ],
)
def test_exponential_backoff(attempt: int, low: int, high: int) -> None:
    """
    Test _exponential_backoff produces times (in ms) in the proper range.
    """
    backoff = round(_exponential_backoff(attempt))
    assert backoff >= low
    assert backoff <= high


class RetryClass:
    def __init__(self) -> None:
        self.attempts = 0

    async def fake_request(self, status: int) -> RetryClass:
        self.status = status
        self.attempts += 1
        return self


async def test_retry_50x_with_503() -> None:
    fake_client = RetryClass()
    resp = await retry_50x(fake_client.fake_request, 503)
    assert resp.attempts == 5


async def test_retry_50x_with_200() -> None:
    fake_client = RetryClass()
    resp = await retry_50x(fake_client.fake_request, 200)
    assert resp.attempts == 1


async def test_retry_50x_with_400() -> None:
    fake_client = RetryClass()
    resp = await retry_50x(fake_client.fake_request, 400)
    assert resp.attempts == 1
