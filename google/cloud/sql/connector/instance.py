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
from enum import Enum
import logging
import re
import ssl
from tempfile import TemporaryDirectory
from typing import Any, Dict, Tuple, TYPE_CHECKING

import aiohttp

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.exceptions import AutoIAMAuthNotSupported
from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError
from google.cloud.sql.connector.exceptions import TLSVersionError
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.cloud.sql.connector.refresh_utils import _is_valid
from google.cloud.sql.connector.refresh_utils import _seconds_until_refresh
from google.cloud.sql.connector.utils import write_to_file

if TYPE_CHECKING:
    import datetime

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


class IPTypes(Enum):
    PUBLIC: str = "PRIMARY"
    PRIVATE: str = "PRIVATE"
    PSC: str = "PSC"

    @classmethod
    def _missing_(cls, value: object) -> None:
        raise ValueError(
            f"Incorrect value for ip_type, got '{value}'. Want one of: "
            f"{', '.join([repr(m.value) for m in cls])}, 'PUBLIC'."
        )

    @classmethod
    def _from_str(cls, ip_type_str: str) -> IPTypes:
        """Convert IP type from a str into IPTypes."""
        if ip_type_str.upper() == "PUBLIC":
            ip_type_str = "PRIMARY"
        return cls(ip_type_str.upper())


class ConnectionInfo:
    ip_addrs: Dict[str, Any]
    context: ssl.SSLContext
    database_version: str
    expiration: datetime.datetime

    def __init__(
        self,
        ephemeral_cert: str,
        database_version: str,
        ip_addrs: Dict[str, Any],
        private_key: bytes,
        server_ca_cert: str,
        expiration: datetime.datetime,
        enable_iam_auth: bool,
    ) -> None:
        self.ip_addrs = ip_addrs
        self.database_version = database_version
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        # update ssl.PROTOCOL_TLS_CLIENT default
        self.context.check_hostname = False

        # verify OpenSSL version supports TLSv1.3
        if ssl.HAS_TLSv1_3:
            # force TLSv1.3 if supported by client
            self.context.minimum_version = ssl.TLSVersion.TLSv1_3
        # fallback to TLSv1.2 for older versions of OpenSSL
        else:
            if enable_iam_auth:
                raise TLSVersionError(
                    f"Your current version of OpenSSL ({ssl.OPENSSL_VERSION}) does not "
                    "support TLSv1.3, which is required to use IAM Authentication.\n"
                    "Upgrade your OpenSSL version to 1.1.1 for TLSv1.3 support."
                )
            logger.warning(
                "TLSv1.3 is not supported with your version of OpenSSL "
                f"({ssl.OPENSSL_VERSION}), falling back to TLSv1.2\n"
                "Upgrade your OpenSSL version to 1.1.1 for TLSv1.3 support."
            )
            self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.expiration = expiration

        # tmpdir and its contents are automatically deleted after the CA cert
        # and ephemeral cert are loaded into the SSLcontext. The values
        # need to be written to files in order to be loaded by the SSLContext
        with TemporaryDirectory() as tmpdir:
            ca_filename, cert_filename, key_filename = write_to_file(
                tmpdir, server_ca_cert, ephemeral_cert, private_key
            )
            self.context.load_cert_chain(cert_filename, keyfile=key_filename)
            self.context.load_verify_locations(cafile=ca_filename)

    def get_preferred_ip(self, ip_type: IPTypes) -> str:
        """Returns the first IP address for the instance, according to the preference
        supplied by ip_type. If no IP addressess with the given preference are found,
        an error is raised."""
        if ip_type.value in self.ip_addrs:
            return self.ip_addrs[ip_type.value]
        raise CloudSQLIPTypeError(
            "Cloud SQL instance does not have any IP addresses matching "
            f"preference: {ip_type.value})"
        )


class Instance:
    """A class to manage the details of the connection to a Cloud SQL
    instance, including refreshing the credentials.

    :param instance_connection_string:
        The Google Cloud SQL Instance's connection
        string.
    :type instance_connection_string: str

    :param enable_iam_auth
        Enables automatic IAM database authentication for Postgres or MySQL
        instances.
    :type enable_iam_auth: bool
    """

    _enable_iam_auth: bool
    _keys: asyncio.Future
    _instance_connection_string: str
    _instance: str
    _project: str
    _region: str

    _refresh_rate_limiter: AsyncRateLimiter
    _refresh_in_progress: asyncio.locks.Event
    _current: asyncio.Task  # task wraps coroutine that returns ConnectionInfo
    _next: asyncio.Task  # task wraps coroutine that returns another task

    def __init__(
        self,
        instance_connection_string: str,
        client: CloudSQLClient,
        keys: asyncio.Future,
        enable_iam_auth: bool = False,
    ) -> None:
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
        self._current = self._schedule_refresh(0)
        self._next = self._current

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

        :rtype: ConnectionInfo
        :returns: A dataclass containing a string representing the ephemeral certificate, a dict
            containing the instances IP adresses, a string representing a PEM-encoded private key
            and a string representing a PEM-encoded certificate authority.
        """
        self._refresh_in_progress.set()
        logger.debug(
            f"['{self._instance_connection_string}']: Entered _perform_refresh"
        )

        try:
            await self._refresh_rate_limiter.acquire()
            priv_key, pub_key = await self._keys

            logger.debug(f"['{self._instance_connection_string}']: Creating context")

            metadata_task = asyncio.create_task(
                self._client._get_metadata(
                    self._project,
                    self._region,
                    self._instance,
                )
            )

            ephemeral_task = asyncio.create_task(
                self._client._get_ephemeral(
                    self._project,
                    self._instance,
                    pub_key,
                    self._enable_iam_auth,
                )
            )
            try:
                metadata = await metadata_task
                # check if automatic IAM database authn is supported for database engine
                if self._enable_iam_auth and not metadata[
                    "database_version"
                ].startswith(("POSTGRES", "MYSQL")):
                    raise AutoIAMAuthNotSupported(
                        f"'{metadata['database_version']}' does not support automatic IAM authentication. It is only supported with Cloud SQL Postgres or MySQL instances."
                    )
            except Exception:
                # cancel ephemeral cert task if exception occurs before it is awaited
                ephemeral_task.cancel()
                raise

            ephemeral_cert, expiration = await ephemeral_task

        except aiohttp.ClientResponseError as e:
            logger.debug(
                f"['{self._instance_connection_string}']: Error occurred during _perform_refresh."
            )
            if e.status == 403:
                e.message = "Forbidden: Authenticated IAM principal does not seeem authorized to make API request. Verify 'Cloud SQL Admin API' is enabled within your GCP project and 'Cloud SQL Client' role has been granted to IAM principal."
            raise

        except Exception:
            logger.debug(
                f"['{self._instance_connection_string}']: Error occurred during _perform_refresh."
            )
            raise

        finally:
            self._refresh_in_progress.clear()

        return ConnectionInfo(
            ephemeral_cert,
            metadata["database_version"],
            metadata["ip_addresses"],
            priv_key,
            metadata["server_ca_cert"],
            expiration,
            self._enable_iam_auth,
        )

    def _schedule_refresh(self, delay: int) -> asyncio.Task:
        """
        Schedule task to sleep and then perform refresh to get ConnectionInfo.

        :type delay: int
        :param delay
            Time in seconds to sleep before running _perform_refresh.

        :rtype: asyncio.Task
        :returns: A Task representing the scheduled _perform_refresh.
        """

        async def _refresh_task(self: Instance, delay: int) -> ConnectionInfo:
            """
            A coroutine that sleeps for the specified amount of time before
            running _perform_refresh.
            """
            refresh_task: asyncio.Task
            try:
                logger.debug(f"['{self._instance_connection_string}']: Entering sleep")
                if delay > 0:
                    await asyncio.sleep(delay)
                refresh_task = asyncio.create_task(self._perform_refresh())
                refresh_data = await refresh_task
            except asyncio.CancelledError:
                logger.debug(
                    f"['{self._instance_connection_string}']: Schedule refresh task cancelled."
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
            self._next = self._schedule_refresh(delay)

            return refresh_data

        # schedule refresh task and return it
        scheduled_task = asyncio.create_task(_refresh_task(self, delay))
        return scheduled_task

    async def connect_info(
        self,
        ip_type: IPTypes,
    ) -> Tuple[ConnectionInfo, str]:
        """Retrieve instance metadata and ip address required
        for making connection to Cloud SQL instance.

        :type ip_type: IPTypes
        :param ip_type: Enum specifying whether to look for public
            or private IP address.

        :rtype instance_data: ConnectionInfo
        :returns: Instance metadata for Cloud SQL instance.

        :rtype ip_address: str
        :returns: A string representing the IP address of
            the given Cloud SQL instance.
        """
        logger.debug(
            f"['{self._instance_connection_string}']: Entered connect_info method"
        )

        instance_data: ConnectionInfo

        instance_data = await self._current
        ip_address: str = instance_data.get_preferred_ip(ip_type)
        return instance_data, ip_address

    async def close(self) -> None:
        """Cleanup function to make sure ClientSession is closed and tasks have
        finished to have a graceful exit.
        """
        logger.debug(
            f"['{self._instance_connection_string}']: Waiting for _current to be cancelled"
        )
        self._current.cancel()
        logger.debug(
            f"['{self._instance_connection_string}']: Waiting for _next to be cancelled"
        )
        self._next.cancel()
        logger.debug(
            f"['{self._instance_connection_string}']: Waiting for _client_session to close"
        )
        # gracefully wait for tasks to cancel
        tasks = asyncio.gather(self._current, self._next, return_exceptions=True)
        await asyncio.wait_for(tasks, timeout=2.0)
