# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

import aiohttp
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate
import google.auth.transport.requests

from google.cloud.sql.connector.refresh_utils import _downscope_credentials
from google.cloud.sql.connector.version import __version__ as version

if TYPE_CHECKING:
    from google.auth.credentials import Credentials

USER_AGENT: str = f"cloud-sql-python-connector/{version}"
API_VERSION: str = "v1beta4"

logger = logging.getLogger(name=__name__)


def _format_user_agent(driver: Optional[str], custom: Optional[str]) -> str:
    agent = f"{USER_AGENT}+{driver}" if driver else USER_AGENT
    if custom:
        agent = f"{agent} {custom}"
    return agent


class CloudSQLClient:
    def __init__(
        self,
        sqladmin_api_endpoint: str,
        quota_project: Optional[str],
        credentials: Credentials,
        client: Optional[aiohttp.ClientSession] = None,
        driver: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Establish the client to be used for Cloud SQL Admin API requests.

        Args:
            sqladmin_api_endpoint (str): Base URL to use when calling
                the Cloud SQL Admin API endpoints.
            quota_project (str): The Project ID for an existing Google Cloud
                project. The project specified is used for quota and
                billing purposes.
            credentials (google.auth.credentials.Credentials):
                A credentials object created from the google-auth Python library.
                Must have the Cloud SQL Admin scopes. For more info check out
                https://google-auth.readthedocs.io/en/latest/.
            client (aiohttp.ClientSession): Async client used to make requests to
                Cloud SQL Admin APIs.
                Optional, defaults to None and creates new client.
            driver (str): Database driver to be used by the client.
        """
        user_agent = _format_user_agent(driver, user_agent)
        headers = {
            "x-goog-api-client": user_agent,
            "User-Agent": user_agent,
            "Content-Type": "application/json",
        }
        if quota_project:
            headers["x-goog-user-project"] = quota_project

        self._client = client if client else aiohttp.ClientSession(headers=headers)
        self._credentials = credentials
        self._sqladmin_api_endpoint = sqladmin_api_endpoint
        self._user_agent = user_agent

    async def _get_metadata(
        self,
        project: str,
        region: str,
        instance: str,
    ) -> Dict[str, Any]:
        """Requests metadata from the Cloud SQL Instance
        and returns a dictionary containing the IP addresses and certificate
        authority of the Cloud SQL Instance.

        :type project: str
        :param project:
            A string representing the name of the project.

        :type region: str
        :param region : A string representing the name of the region.

        :type instance: str
        :param instance: A string representing the name of the instance.

        :rtype: Dict[str: Union[Dict, str]]
        :returns: Returns a dictionary containing a dictionary of all IP
            addresses and their type and a string representing the
            certificate authority.
        """
        if not self._credentials.valid:
            request = google.auth.transport.requests.Request()
            self._credentials.refresh(request)

        headers = {
            "Authorization": f"Bearer {self._credentials.token}",
        }

        url = f"{self._sqladmin_api_endpoint}/sql/{API_VERSION}/projects/{project}/instances/{instance}/connectSettings"

        logger.debug(f"['{instance}']: Requesting metadata")

        resp = await self._client.get(url, headers=headers, raise_for_status=True)
        ret_dict = await resp.json()

        if ret_dict["region"] != region:
            raise ValueError(
                f'[{project}:{region}:{instance}]: Provided region was mismatched - got region {region}, expected {ret_dict["region"]}.'
            )

        ip_addresses = (
            {ip["type"]: ip["ipAddress"] for ip in ret_dict["ipAddresses"]}
            if "ipAddresses" in ret_dict
            else {}
        )
        if "dnsName" in ret_dict:
            ip_addresses["PSC"] = ret_dict["dnsName"]

        return {
            "ip_addresses": ip_addresses,
            "server_ca_cert": ret_dict["serverCaCert"]["cert"],
            "database_version": ret_dict["databaseVersion"],
        }

    async def _get_ephemeral(
        self,
        project: str,
        instance: str,
        pub_key: str,
        enable_iam_auth: bool = False,
    ) -> Tuple[str, datetime.datetime]:
        """Asynchronously requests an ephemeral certificate from the Cloud SQL Instance.

        :type project: str
        :param project : A string representing the name of the project.

        :type instance: str
        :param instance: A string representing the name of the instance.

        :type pub_key:
        :param str: A string representing PEM-encoded RSA public key.

        :type enable_iam_auth: bool
        :param enable_iam_auth
            Enables automatic IAM database authentication for Postgres or MySQL
            instances.

        :rtype: str
        :returns: An ephemeral certificate from the Cloud SQL instance that allows
            authorized connections to the instance.
        """

        logger.debug(f"['{instance}']: Requesting ephemeral certificate")

        if not self._credentials.valid:
            request = google.auth.transport.requests.Request()
            self._credentials.refresh(request)

        headers = {
            "Authorization": f"Bearer {self._credentials.token}",
        }

        url = f"{self._sqladmin_api_endpoint}/sql/{API_VERSION}/projects/{project}/instances/{instance}:generateEphemeralCert"

        data = {"public_key": pub_key}

        if enable_iam_auth:
            # down-scope credentials with only IAM login scope (refreshes them too)
            login_creds = _downscope_credentials(self._credentials)
            data["access_token"] = login_creds.token

        resp = await self._client.post(
            url, headers=headers, json=data, raise_for_status=True
        )

        ret_dict = await resp.json()

        ephemeral_cert: str = ret_dict["ephemeralCert"]["cert"]

        # decode cert to read expiration
        x509 = load_pem_x509_certificate(
            ephemeral_cert.encode("UTF-8"), default_backend()
        )
        expiration = x509.not_valid_after_utc
        # for IAM authentication OAuth2 token is embedded in cert so it
        # must still be valid for successful connection
        if enable_iam_auth:
            token_expiration: datetime.datetime = login_creds.expiry
            # google.auth library strips timezone info for backwards compatibality
            # reasons with Python 2. Add it back to allow timezone aware datetimes.
            # Ref: https://github.com/googleapis/google-auth-library-python/blob/49a5ff7411a2ae4d32a7d11700f9f961c55406a9/google/auth/_helpers.py#L93-L99
            token_expiration = token_expiration.replace(tzinfo=datetime.timezone.utc)

            if expiration > token_expiration:
                expiration = token_expiration
        return ephemeral_cert, expiration

    async def close(self) -> None:
        """Close CloudSQLClient gracefully."""
        await self._client.close()
