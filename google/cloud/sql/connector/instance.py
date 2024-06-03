"""
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

from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import logging
import re
from typing import Tuple

import aiohttp

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.exceptions import RefreshNotValidError
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.cloud.sql.connector.refresh_utils import _is_valid
from google.cloud.sql.connector.refresh_utils import _seconds_until_refresh

logger = logging.getLogger(name=__name__)

APPLICATION_NAME = "cloud-sql-python-connector"

# Instance connection name is the format <PROJECT>:<REGION>:<INSTANCE>
# Additionally, we have to support legacy "domain-scoped" projects
# (e.g. "google.com:PROJECT")
CONN_NAME_REGEX = re.compile(("([^:]+(:[^:]+)?):([^:]+):([^:]+)"))


def _parse_instance_connection_name(connection_name: str) -> Tuple[str, str, str]:
    if CONN_NAME_REGEX.fullmatch(connection_name) is None:
        raise ValueError(
            "Arg `instance_connection_string` must have "
            "format: PROJECT:REGION:INSTANCE, "
            f"got {connection_name}."
        )
    connection_name_split = CONN_NAME_REGEX.split(connection_name)
    return connection_name_split[1], connection_name_split[3], connection_name_split[4]


class RefreshAheadCache:
    """Cache that refreshes connection info in the background prior to expiration.

    Background tasks are used to schedule refresh attempts to get a new
    ephemeral certificate and Cloud SQL metadata (IP addresses, etc.) ahead of
    expiration.
    """

    def __init__(
        self,
        instance_connection_string: str,
        client: CloudSQLClient,
        keys: asyncio.Future,
        enable_iam_auth: bool = False,
    ) -> None:
        """Initializes a RefreshAheadCache instance.

        Args:
            instance_connection_string (str): The Cloud SQL Instance's
                connection string (also known as an instance connection name).
            client (CloudSQLClient): The Cloud SQL Client instance.
            keys (asyncio.Future): A future to the client's public-private key
                pair.
            enable_iam_auth (bool): Enables automatic IAM database authentication
                (Postgres and MySQL) as the default authentication method for all
                connections.
        """
        # validate and parse instance connection name
        self._project, self._region, self._instance = _parse_instance_connection_name(
            instance_connection_string
        )
        self._instance_connection_string = instance_connection_string

        self._enable_iam_auth = enable_iam_auth
        self._keys = keys
        self._client = client
        self._refresh_rate_limiter = AsyncRateLimiter(
            max_capacity=2,
            rate=1 / 30,
        )
        self._refresh_in_progress = asyncio.locks.Event()
        self._current: asyncio.Task = self._schedule_refresh(0)
        self._next: asyncio.Task = self._current

    async def force_refresh(self) -> None:
        """
        Forces a new refresh attempt immediately to be used for future connection attempts.
        """
        # if next refresh is not already in progress, cancel it and schedule new one immediately
        if not self._refresh_in_progress.is_set():
            self._next.cancel()
            self._next = self._schedule_refresh(0)
        # block all sequential connection attempts on the next refresh result if current is invalid
        if not await _is_valid(self._current):
            self._current = self._next

    async def _perform_refresh(self) -> ConnectionInfo:
        """Retrieves instance metadata and ephemeral certificate from the
        Cloud SQL Instance.

        Returns:
            A ConnectionInfo instance containing a string representing the
            ephemeral certificate, a dict containing the instances IP adresses,
            a string representing a PEM-encoded private key and a string
            representing a PEM-encoded certificate authority.
        """
        self._refresh_in_progress.set()
        logger.debug(
            f"['{self._instance_connection_string}']: Connection info refresh "
            "operation started"
        )

        try:
            await self._refresh_rate_limiter.acquire()
            connection_info = await self._client.get_connection_info(
                self._project,
                self._region,
                self._instance,
                self._keys,
                self._enable_iam_auth,
            )
            logger.debug(
                f"['{self._instance_connection_string}']: Connection info "
                "refresh operation complete"
            )
            logger.debug(
                f"['{self._instance_connection_string}']: Current certificate "
                f"expiration = {connection_info.expiration.isoformat()}"
            )

        except aiohttp.ClientResponseError as e:
            logger.debug(
                f"['{self._instance_connection_string}']: Connection info "
                f"refresh operation failed: {str(e)}"
            )
            if e.status == 403:
                e.message = "Forbidden: Authenticated IAM principal does not seeem authorized to make API request. Verify 'Cloud SQL Admin API' is enabled within your GCP project and 'Cloud SQL Client' role has been granted to IAM principal."
            raise

        except Exception as e:
            logger.debug(
                f"['{self._instance_connection_string}']: Connection info "
                f"refresh operation failed: {str(e)}"
            )
            raise

        finally:
            self._refresh_in_progress.clear()
        return connection_info

    def _schedule_refresh(self, delay: int) -> asyncio.Task:
        """
        Schedule task to sleep and then perform refresh to get ConnectionInfo.

        Args:
            delay (int): Time in seconds to sleep before performing a refresh.

        Returns:
            An asyncio.Task representing the scheduled refresh.
        """

        async def _refresh_task(self: RefreshAheadCache, delay: int) -> ConnectionInfo:
            """
            A coroutine that sleeps for the specified amount of time before
            running _perform_refresh.
            """
            refresh_task: asyncio.Task
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                refresh_task = asyncio.create_task(self._perform_refresh())
                refresh_data = await refresh_task
                # check that refresh is valid
                if not await _is_valid(refresh_task):
                    raise RefreshNotValidError(
                        f"['{self._instance_connection_string}']: Invalid refresh operation. Certficate appears to be expired."
                    )
            except asyncio.CancelledError:
                logger.debug(
                    f"['{self._instance_connection_string}']: Scheduled refresh"
                    " operation cancelled"
                )
                raise
            # bad refresh attempt
            except Exception as e:
                logger.exception(
                    f"['{self._instance_connection_string}']: "
                    "An error occurred while performing refresh. "
                    "Scheduling another refresh attempt immediately",
                    exc_info=e,
                )
                # check if current metadata is invalid (expired),
                # don't want to replace valid metadata with invalid refresh
                if not await _is_valid(self._current):
                    self._current = refresh_task
                # schedule new refresh attempt immediately
                self._next = self._schedule_refresh(0)
                raise
            # if valid refresh, replace current with valid metadata and schedule next refresh
            self._current = refresh_task
            # calculate refresh delay based on certificate expiration
            delay = _seconds_until_refresh(refresh_data.expiration)
            logger.debug(
                f"['{self._instance_connection_string}']: Connection info refresh"
                " operation scheduled for "
                f"{(datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec='seconds')} "
                f"(now + {timedelta(seconds=delay)})"
            )
            self._next = self._schedule_refresh(delay)

            return refresh_data

        # schedule refresh task and return it
        scheduled_task = asyncio.create_task(_refresh_task(self, delay))
        return scheduled_task

    async def connect_info(self) -> ConnectionInfo:
        """Retrieves ConnectionInfo instance for establishing a secure
        connection to the Cloud SQL instance.
        """
        return await self._current

    async def close(self) -> None:
        """Cleanup function to make sure tasks have finished to have a
        graceful exit.
        """
        logger.debug(
            f"['{self._instance_connection_string}']: Canceling connection info "
            "refresh operation tasks"
        )
        self._current.cancel()
        self._next.cancel()
        # gracefully wait for tasks to cancel
        tasks = asyncio.gather(self._current, self._next, return_exceptions=True)
        await asyncio.wait_for(tasks, timeout=2.0)
