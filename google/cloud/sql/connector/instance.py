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

# Custom utils import
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.cloud.sql.connector.refresh_utils import (
    _get_ephemeral,
    _get_metadata,
    _seconds_until_refresh,
    _is_valid,
)
from google.cloud.sql.connector.utils import write_to_file
from google.cloud.sql.connector.version import __version__ as version
from google.cloud.sql.connector.exceptions import (
    TLSVersionError,
    CloudSQLIPTypeError,
    CredentialsTypeError,
    AutoIAMAuthNotSupported,
)

# Importing libraries
import asyncio
import aiohttp
import datetime
from enum import Enum
import google.auth
from google.auth.credentials import Credentials, with_scopes_if_required
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
import google.auth.transport.requests
import ssl
from tempfile import TemporaryDirectory
from typing import (
    Any,
    Dict,
    Optional,
    Tuple,
)
import logging

logger = logging.getLogger(name=__name__)

APPLICATION_NAME = "cloud-sql-python-connector"


class IPTypes(Enum):
    PUBLIC: str = "PRIMARY"
    PRIVATE: str = "PRIVATE"


class InstanceMetadata:
    ip_addrs: Dict[str, Any]
    context: ssl.SSLContext
    expiration: datetime.datetime

    def __init__(
        self,
        ephemeral_cert: str,
        ip_addrs: Dict[str, Any],
        private_key: bytes,
        server_ca_cert: str,
        expiration: datetime.datetime,
        enable_iam_auth: bool,
    ) -> None:
        self.ip_addrs = ip_addrs
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS)

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

        # add request_ssl attribute to ssl.SSLContext, required for pg8000 driver
        self.context.request_ssl = False  # type: ignore

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

    :param user_agent_string:
        The user agent string to append to SQLAdmin API requests
    :type user_agent_string: str

    :type credentials: google.auth.credentials.Credentials
    :param credentials
        Credentials object used to authenticate connections to Cloud SQL server.
        If not specified, Application Default Credentials are used.

    :param enable_iam_auth
        Enables IAM based authentication for Postgres instances.
    :type enable_iam_auth: bool

    :param loop:
        A new event loop for the refresh function to run in.
    :type loop: asyncio.AbstractEventLoop

    :type quota_project: str
    :param quota_project
        The Project ID for an existing Google Cloud project. The project specified
        is used for quota and billing purposes. If not specified, defaults to
        project sourced from environment.

    :type sqladmin_api_endpoint: str
    :param sqladmin_api_endpoint:
        Base URL to use when calling the Cloud SQL Admin API endpoint.
        Defaults to "https://sqladmin.googleapis.com", this argument should
        only be used in development.
    """

    # asyncio.AbstractEventLoop is used because the default loop,
    # SelectorEventLoop, is usable on both Unix and Windows but has limited
    # functionality on Windows. It is recommended to use ProactorEventLoop
    # while developing on Windows.
    # Link to Github issue:
    # https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/22
    _loop: asyncio.AbstractEventLoop

    _enable_iam_auth: bool

    __client_session: Optional[aiohttp.ClientSession] = None

    @property
    def _client_session(self) -> aiohttp.ClientSession:
        if self.__client_session is None:
            headers = {
                "x-goog-api-client": self._user_agent_string,
                "User-Agent": self._user_agent_string,
                "Content-Type": "application/json",
            }
            if self._quota_project:
                headers["x-goog-user-project"] = self._quota_project
            self.__client_session = aiohttp.ClientSession(headers=headers)
        return self.__client_session

    _credentials: Optional[Credentials] = None
    _keys: asyncio.Future

    _instance_connection_string: str
    _user_agent_string: str
    _sqladmin_api_endpoint: str
    _instance: str
    _project: str
    _region: str

    _refresh_rate_limiter: AsyncRateLimiter
    _refresh_in_progress: asyncio.locks.Event
    _current: asyncio.Task  # task wraps coroutine that returns InstanceMetadata
    _next: asyncio.Task  # task wraps coroutine that returns another task

    def __init__(
        self,
        instance_connection_string: str,
        driver_name: str,
        keys: asyncio.Future,
        loop: asyncio.AbstractEventLoop,
        credentials: Optional[Credentials] = None,
        enable_iam_auth: bool = False,
        quota_project: str = None,
        sqladmin_api_endpoint: str = "https://sqladmin.googleapis.com",
    ) -> None:
        # Validate connection string
        connection_string_split = instance_connection_string.split(":")

        if len(connection_string_split) == 3:
            self._instance_connection_string = instance_connection_string
            self._project = connection_string_split[0]
            self._region = connection_string_split[1]
            self._instance = connection_string_split[2]
        else:
            raise ValueError(
                "Arg `instance_connection_string` must have "
                "format: PROJECT:REGION:INSTANCE, "
                f"got {instance_connection_string}."
            )

        self._enable_iam_auth = enable_iam_auth

        self._user_agent_string = f"{APPLICATION_NAME}/{version}+{driver_name}"
        self._quota_project = quota_project
        self._sqladmin_api_endpoint = sqladmin_api_endpoint
        self._loop = loop
        self._keys = keys
        # validate credentials type
        if not isinstance(credentials, Credentials) and credentials is not None:
            raise CredentialsTypeError(
                "Arg credentials must be type 'google.auth.credentials.Credentials' "
                "or None (to use Application Default Credentials)"
            )

        self._auth_init(credentials)

        self._refresh_rate_limiter = AsyncRateLimiter(
            max_capacity=2, rate=1 / 30, loop=self._loop
        )
        self._refresh_in_progress = asyncio.locks.Event()
        self._current = self._schedule_refresh(0)
        self._next = self._current

    def _auth_init(self, credentials: Optional[Credentials]) -> None:
        """Creates and assigns a Google Python API service object for
        Google Cloud SQL Admin API.

        :type credentials: google.auth.credentials.Credentials
        :param credentials
            Credentials object used to authenticate connections to Cloud SQL server.
            If not specified, Application Default Credentials are used.
        """
        scopes = ["https://www.googleapis.com/auth/sqlservice.admin"]
        # if Credentials object is passed in, use for authentication
        if isinstance(credentials, Credentials):
            credentials = with_scopes_if_required(credentials, scopes=scopes)
        # otherwise use application default credentials
        else:
            credentials, project = google.auth.default(scopes=scopes)

        self._credentials = credentials

    def force_refresh(self) -> None:
        """
        Forces a new refresh attempt immediately to be used for future connection attempts.
        """
        # if next refresh is not already in progress, cancel it and schedule new one immediately
        if not self._refresh_in_progress.is_set():
            self._next.cancel()
            self._next = self._schedule_refresh(0)
        # block all sequential connection attempts on the next refresh result
        self._current = self._next

    async def _perform_refresh(self) -> InstanceMetadata:
        """Retrieves instance metadata and ephemeral certificate from the
        Cloud SQL Instance.

        :rtype: InstanceMetadata
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

            metadata_task = self._loop.create_task(
                _get_metadata(
                    self._client_session,
                    self._sqladmin_api_endpoint,
                    self._credentials,
                    self._project,
                    self._instance,
                )
            )

            ephemeral_task = self._loop.create_task(
                _get_ephemeral(
                    self._client_session,
                    self._sqladmin_api_endpoint,
                    self._credentials,
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
                ].startswith("POSTGRES"):
                    raise AutoIAMAuthNotSupported(
                        f"'{metadata['database_version']}' does not support automatic IAM authentication. It is only supported with Cloud SQL Postgres instances."
                    )
            except Exception:
                # cancel ephemeral cert task if exception occurs before it is awaited
                ephemeral_task.cancel()
                raise

            ephemeral_cert = await ephemeral_task

            x509 = load_pem_x509_certificate(
                ephemeral_cert.encode("UTF-8"), default_backend()
            )
            expiration = x509.not_valid_after

            if self._enable_iam_auth:
                if self._credentials is not None:
                    token_expiration: datetime.datetime = self._credentials.expiry
                if expiration > token_expiration:
                    expiration = token_expiration

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

        return InstanceMetadata(
            ephemeral_cert,
            metadata["ip_addresses"],
            priv_key,
            metadata["server_ca_cert"],
            expiration,
            self._enable_iam_auth,
        )

    def _schedule_refresh(self, delay: int) -> asyncio.Task:
        """
        Schedule task to sleep and then perform refresh to get InstanceMetadata.

        :type delay: int
        :param delay
            Time in seconds to sleep before running _perform_refresh.

        :rtype: asyncio.Task
        :returns: A Task representing the scheduled _perform_refresh.
        """

        async def _refresh_task(self: Instance, delay: int) -> InstanceMetadata:
            """
            A coroutine that sleeps for the specified amount of time before
            running _perform_refresh.
            """
            refresh_task: asyncio.Task
            try:
                logger.debug(f"['{self._instance_connection_string}']: Entering sleep")
                if delay > 0:
                    await asyncio.sleep(delay)
                refresh_task = self._loop.create_task(self._perform_refresh())
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
            # Ephemeral certificate expires in 1 hour, so we schedule a refresh to happen in 55 minutes.
            delay = _seconds_until_refresh(
                refresh_data.expiration, self._enable_iam_auth
            )
            self._next = self._schedule_refresh(delay)

            return refresh_data

        # schedule refresh task and return it
        scheduled_task = self._loop.create_task(_refresh_task(self, delay))
        return scheduled_task

    async def connect_info(
        self,
        ip_type: IPTypes,
    ) -> Tuple[InstanceMetadata, str]:
        """Retrieve instance metadata and ip address required
        for making connection to Cloud SQL instance.

        :type ip_type: IPTypes
        :param ip_type: Enum specifying whether to look for public
            or private IP address.

        :rtype instance_data: InstanceMetadata
        :returns: Instance metadata for Cloud SQL instance.

        :rtype ip_address: str
        :returns: A string representing the IP address of
            the given Cloud SQL instance.
        """
        logger.debug(
            f"['{self._instance_connection_string}']: Entered connect_info method"
        )

        instance_data: InstanceMetadata

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
        await self._client_session.close()
