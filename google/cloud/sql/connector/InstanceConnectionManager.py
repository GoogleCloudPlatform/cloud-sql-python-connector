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

import asyncio
import aiohttp
import googleapiclient
import googleapiclient.discovery
import google.auth
from google.auth.credentials import Credentials
from google.cloud.sql.connector.utils import generate_keys
import google.auth.transport.requests
import json
from typing import Dict, Union


class CloudSQLConnectionError(Exception):
    """
    Raised when the provided connection string is not formatted
    correctly.
    """

    def __init__(self, *args, **kwargs) -> None:
        super(CloudSQLConnectionError, self).__init__(self, *args, **kwargs)


class InstanceConnectionManager:
    """A class to manage the details of the connection, including refreshing the
    credentials.

    :param instance_connection_string:
        The Google Cloud SQL Instance's connection
        string.
    :type instance_connection_string: str
    :param loop:
        A new event loop for the refresh function to run in.
    :type loop: asyncio.AbstractEventLoop
    """

    # asyncio.AbstractEventLoop is used because the default loop,
    # SelectorEventLoop, is usable on both Unix and Windows but has limited
    # functionality on Windows. It is recommended to use ProactorEventLoop
    # while developing on Windows.
    _loop: asyncio.AbstractEventLoop = None
    _instance_connection_string: str = None
    _project: str = None
    _region: str = None
    _instance: str = None
    _credentials: Credentials = None
    _priv_key: str = None
    _pub_key: str = None
    _client_session: aiohttp.ClientSession = None

    def __init__(
        self, instance_connection_string: str, loop: asyncio.AbstractEventLoop
    ) -> None:
        # Validate connection string
        connection_string_split = instance_connection_string.split(":")

        if len(connection_string_split) == 3:
            self._instance_connection_string = instance_connection_string
            self._project = connection_string_split[0]
            self._region = connection_string_split[1]
            self._instance = connection_string_split[2]
        else:
            raise CloudSQLConnectionError(
                "Arg instance_connection_string must be in "
                + "format: project:region:instance."
            )
        self._loop = loop
        self._auth_init()
        self._priv_key, self._pub_key = generate_keys()

        # set current to future InstanceMetadata
        # set next to the future future InstanceMetadata

    def __del__(self):
        async def close_client_session():
            await self._client_session.close()

        if self._client_session is not None:
            self._loop.run_until_complete(close_client_session())
            self._loop.stop()

    @staticmethod
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
            "Content-Type": "application/json",
        }

        url = "https://www.googleapis.com/sql/v1beta4/projects/{}/instances/{}".format(
            project, instance
        )

        resp = await client_session.get(url, headers=headers, raise_for_status=True)
        ret_dict = json.loads(await resp.text())

        metadata = {
            "ip_addresses": {
                ip["type"]: ip["ipAddress"] for ip in ret_dict["ipAddresses"]
            },
            "server_ca_cert": ret_dict["serverCaCert"]["cert"],
        }

        return metadata

    @staticmethod
    async def _get_ephemeral(
        client_session: aiohttp.ClientSession,
        credentials: Credentials,
        project: str,
        instance: str,
        pub_key: str,
    ) -> str:
        """Asynchronously requests an ephemeral certificate from the Cloud SQL Instance.

        Args:
            credentials (google.oauth2.service_account.Credentials): A credentials object
              created from the google-auth library. Must be
              using the SQL Admin API scopes. For more info, check out
              https://google-auth.readthedocs.io/en/latest/.
            project (str): A string representing the name of the project.
            instance (str): A string representing the name of the instance.
            pub_key (str): A string representing PEM-encoded RSA public key.

        Returns:
            str
              An ephemeral certificate from the Cloud SQL instance that allows
              authorized connections to the instance.

        Raises:
            TypeError: If one of the arguments passed in is None.
        """

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
            "Content-Type": "application/json",
        }

        url = "https://www.googleapis.com/sql/v1beta4/projects/{}/instances/{}/createEphemeral".format(
            project, instance
        )

        data = {"public_key": pub_key}

        resp = await client_session.post(
            url, headers=headers, json=data, raise_for_status=True
        )
        ret_dict = json.loads(await resp.text())

        return ret_dict["cert"]

    def _auth_init(self):
        """Creates and assigns a Google Python API service object for
        Google Cloud SQL Admin API.
        """

        credentials, project = google.auth.default()
        scoped_credentials = credentials.with_scopes(
            [
                "https://www.googleapis.com/auth/sqlservice.admin",
                "https://www.googleapis.com/auth/cloud-platform",
            ]
        )

        cloudsql = googleapiclient.discovery.build(
            "sqladmin", "v1beta4", credentials=scoped_credentials
        )

        self._credentials = scoped_credentials
        self._cloud_sql_service = cloudsql

    async def _perform_refresh(self) -> Dict[str, Union[Dict, str]]:
        """Retrieves instance metadata and ephemeral certificate from the
        Cloud SQL Instance.

        :rtype: Dict[str, Union[Dict, str]]
        :returns: A Dictionary containing the server's certificate authority,
            a Dictionary containing the IP addresses of the instance, and
            the latest ephemeral certificate.
        """

        if self._client_session is None:
            self._client_session = aiohttp.ClientSession()

        metadata_future = self._get_metadata(
            self._client_session, self._credentials, self._project, self._instance
        )

        ephemeral_future = self._get_ephemeral(
            self._client_session,
            self._credentials,
            self._project,
            self._instance,
            self._pub_key.decode("UTF-8"),
        )

        result_future = asyncio.gather(metadata_future, ephemeral_future)

        return result_future
