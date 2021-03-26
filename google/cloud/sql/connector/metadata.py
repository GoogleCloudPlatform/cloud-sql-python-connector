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
from google.auth.credentials import Credentials
import google.auth.transport.requests
import json
from typing import Dict, Union

import logging

logger = logging.getLogger(name=__name__)

_sql_api_version: str = "v1beta4"


async def _get_metadata(
    client_session: aiohttp.ClientSession,
    credentials: Credentials,
    project: str,
    instance: str,
) -> Dict[str, Union[Dict, str]]:
    """Requests metadata from the Cloud SQL Instance
    and returns a dictionary containing the IP addresses and certificate
    authority of the Cloud SQL Instance.

    :type credentials: google.oauth2.service_account.Credentials
    :param service:
        A credentials object created from the google-auth Python library.
        Must have the SQL Admin API scopes. For more info check out
        https://google-auth.readthedocs.io/en/latest/.

    :type project: str
    :param project:
        A string representing the name of the project.

    :type inst_name: str
    :param project: A string representing the name of the instance.

    :rtype: Dict[str: Union[Dict, str]]
    :returns: Returns a dictionary containing a dictionary of all IP
          addresses and their type and a string representing the
          certificate authority.

    :raises TypeError: If any of the arguments are not the specified type.
    """

    if (
        not isinstance(credentials, Credentials)
        or not isinstance(project, str)
        or not isinstance(instance, str)
    ):
        raise TypeError(
            "Arguments must be as follows: "
            + "service (googleapiclient.discovery.Resource), "
            + "proj_name (str) and inst_name (str)."
        )

    if not credentials.valid:
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)

    headers = {
        "Authorization": "Bearer {}".format(credentials.token),
    }

    url = "https://www.googleapis.com/sql/{}/projects/{}/instances/{}".format(
        _sql_api_version, project, instance
    )

    logger.debug("Requesting metadata")

    resp = await client_session.get(url, headers=headers, raise_for_status=True)
    ret_dict = json.loads(await resp.text())

    metadata = {
        "ip_addresses": {ip["type"]: ip["ipAddress"] for ip in ret_dict["ipAddresses"]},
        "server_ca_cert": ret_dict["serverCaCert"]["cert"],
    }

    return metadata
