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


import aiohttp
import google.auth
from google.auth.credentials import Credentials, Scoped
import google.auth.transport.requests
from typing import Any, Dict, List
import datetime
import copy
import asyncio
import logging

logger = logging.getLogger(name=__name__)

_sql_api_version: str = "v1beta4"

# default_refresh_buffer is the amount of time before a refresh's result expires
# that a new refresh operation begins.
_default_refresh_buffer: int = 5 * 60  # 5 minutes

# _iam_auth_refresh_buffer is the amount of time before a refresh's result expires
# that a new refresh operation begins when IAM DB AuthN is enabled. Because token
# sources may be cached until ~60 seconds before expiration, this value must be smaller
# than default_refresh_buffer.
_iam_auth_refresh_buffer: int = 55  # seconds


async def _get_metadata(
    client_session: aiohttp.ClientSession,
    sqladmin_api_endpoint: str,
    credentials: Credentials,
    project: str,
    instance: str,
) -> Dict[str, Any]:
    """Requests metadata from the Cloud SQL Instance
    and returns a dictionary containing the IP addresses and certificate
    authority of the Cloud SQL Instance.

    :type sqladmin_api_endpoint: str
    :param sqladmin_api_endpoint:
        Base URL to use when calling the Cloud SQL Admin API endpoint.

    :type credentials: google.auth.credentials.Credentials
    :param credentials:
        A credentials object created from the google-auth Python library.
        Must have the SQL Admin API scopes. For more info check out
        https://google-auth.readthedocs.io/en/latest/.

    :type project: str
    :param project:
        A string representing the name of the project.

    :type instance: str
    :param instance: A string representing the name of the instance.

    :rtype: Dict[str: Union[Dict, str]]
    :returns: Returns a dictionary containing a dictionary of all IP
          addresses and their type and a string representing the
          certificate authority.

    :raises TypeError: If any of the arguments are not the specified type.
    """

    if not isinstance(credentials, Credentials):
        raise TypeError(
            "credentials must be of type google.auth.credentials.Credentials,"
            f" got {type(credentials)}"
        )
    elif not isinstance(project, str):
        raise TypeError(f"project must be of type str, got {type(project)}")
    elif not isinstance(instance, str):
        raise TypeError(f"instance must be of type str, got {type(instance)}")

    if not credentials.valid:
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)

    headers = {
        "Authorization": "Bearer {}".format(credentials.token),
    }

    url = "{}/sql/{}/projects/{}/instances/{}/connectSettings".format(
        sqladmin_api_endpoint, _sql_api_version, project, instance
    )

    logger.debug(f"['{instance}']: Requesting metadata")

    resp = await client_session.get(url, headers=headers, raise_for_status=True)
    ret_dict = await resp.json()

    metadata = {
        "ip_addresses": {ip["type"]: ip["ipAddress"] for ip in ret_dict["ipAddresses"]},
        "server_ca_cert": ret_dict["serverCaCert"]["cert"],
        "database_version": ret_dict["databaseVersion"],
    }

    return metadata


async def _get_ephemeral(
    client_session: aiohttp.ClientSession,
    sqladmin_api_endpoint: str,
    credentials: Credentials,
    project: str,
    instance: str,
    pub_key: str,
    enable_iam_auth: bool = False,
) -> str:
    """Asynchronously requests an ephemeral certificate from the Cloud SQL Instance.

    :type sqladmin_api_endpoint: str
    :param sqladmin_api_endpoint:
        Base URL to use when calling the Cloud SQL Admin API endpoint.

    :type credentials: google.auth.credentials.Credentials
    :param credentials: A credentials object
        created from the google-auth library. Must be
        using the SQL Admin API scopes. For more info, check out
        https://google-auth.readthedocs.io/en/latest/.

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

    :raises TypeError: If one of the arguments passed in is None.
    """

    logger.debug(f"['{instance}']: Requesting ephemeral certificate")

    if not isinstance(credentials, Credentials):
        raise TypeError(
            "credentials must be of type google.auth.credentials.Credentials,"
            f" got {type(credentials)}"
        )
    elif not isinstance(project, str):
        raise TypeError(f"project must be of type str, got {type(project)}")
    elif not isinstance(instance, str):
        raise TypeError(f"instance must be of type str, got {type(instance)}")
    elif not isinstance(pub_key, str):
        raise TypeError(f"pub_key must be of type str, got {type(pub_key)}")

    if not credentials.valid:
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)

    headers = {
        "Authorization": f"Bearer {credentials.token}",
    }

    url = "{}/sql/{}/projects/{}/instances/{}:generateEphemeralCert".format(
        sqladmin_api_endpoint, _sql_api_version, project, instance
    )

    data = {"public_key": pub_key}

    if enable_iam_auth:
        # down-scope credentials with only IAM login scope (refreshes them too)
        login_creds = _downscope_credentials(credentials)
        data["access_token"] = login_creds.token

    resp = await client_session.post(
        url, headers=headers, json=data, raise_for_status=True
    )

    ret_dict = await resp.json()

    return ret_dict["ephemeralCert"]["cert"]


def _seconds_until_refresh(
    expiration: datetime.datetime,
    enable_iam_auth: bool,
) -> int:
    """
    Helper function to get time in seconds before performing next refresh.

    :rtype: int
    :returns: Time in seconds to wait before performing next refresh.
    """
    if enable_iam_auth:
        refresh_buffer = _iam_auth_refresh_buffer
    else:
        refresh_buffer = _default_refresh_buffer

    delay = (expiration - datetime.datetime.now()) - datetime.timedelta(
        seconds=refresh_buffer
    )

    if delay.total_seconds() < 0:
        # If the time until the certificate expires is less than the buffer,
        # schedule the refresh closer to the expiration time
        delay = (expiration - datetime.datetime.now()) - datetime.timedelta(seconds=5)

    return int(delay.total_seconds())


async def _is_valid(task: asyncio.Task) -> bool:
    try:
        metadata = await task
        # only valid if now is before the cert expires
        if datetime.datetime.now() < metadata.expiration:
            return True
    except Exception:
        # supress any errors from task
        logger.debug("Current instance metadata is invalid.")
    return False


def _downscope_credentials(
    credentials: Credentials,
    scopes: List[str] = ["https://www.googleapis.com/auth/sqlservice.login"],
) -> Credentials:
    """Generate a down-scoped credential.

    :type credentials: google.auth.credentials.Credentials
    :param credentials
        Credentials object used to generate down-scoped credentials.

    :type scopes: List[str]
    :param scopes
        List of Google scopes to include in down-scoped credentials object.

    :rtype: google.auth.credentials.Credentials
    :returns: Down-scoped credentials object.
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
        scoped_creds._scopes = scopes
    # down-scoped credentials require refresh, are invalid after being re-scoped
    if not scoped_creds.valid:
        request = google.auth.transport.requests.Request()
        scoped_creds.refresh(request)
    return scoped_creds
