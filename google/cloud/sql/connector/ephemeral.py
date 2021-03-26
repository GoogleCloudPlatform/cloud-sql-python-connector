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

# Importing libraries
import asyncio
import aiohttp
import concurrent
import google.auth
from google.auth.credentials import Credentials
import google.auth.transport.requests
import json
import ssl
import socket
from tempfile import NamedTemporaryFile
import threading
from typing import Any

import logging

logger = logging.getLogger(name=__name__)

_sql_api_version: str = "v1beta4"

async def _get_ephemeral(
    client_session: aiohttp.ClientSession,
    credentials: Credentials,
    project: str,
    instance: str,
    pub_key: str,
) -> str:
    """Asynchronously requests an ephemeral certificate from the Cloud SQL Instance.

    :type credentials: google.oauth2.service_account.Credentials
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

    :rtype: str
    :returns: An ephemeral certificate from the Cloud SQL instance that allows
          authorized connections to the instance.

    :raises TypeError: If one of the arguments passed in is None.
    """

    logger.debug("Requesting ephemeral certificate")

    if (
        not isinstance(credentials, Credentials)
        or not isinstance(project, str)
        or not isinstance(instance, str)
        or not isinstance(pub_key, str)
    ):
        raise TypeError("Cannot take None as an argument.")

    if not credentials.valid:
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)

    headers = {
        "Authorization": "Bearer {}".format(credentials.token),
    }

    url = "https://www.googleapis.com/sql/{}/projects/{}/instances/{}/createEphemeral".format(
        _sql_api_version, project, instance
    )

    data = {"public_key": pub_key}

    resp = await client_session.post(
        url, headers=headers, json=data, raise_for_status=True
    )

    ret_dict = json.loads(await resp.text())

    return ret_dict["cert"]
