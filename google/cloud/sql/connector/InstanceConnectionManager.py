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
import googleapiclient
import googleapiclient.discovery
import google.auth
from google.auth.credentials import Credentials
from typing import Dict, Union
from googleapiclient.discovery import Resource


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

        self._auth_init()

        # set current to future InstanceMetadata
        # set next to the future future InstanceMetadata

    def _get_metadata(
        service: Resource, project: str, instance: str
    ) -> Dict[str, Union[Dict, str]]:
        """Requests metadata from the Cloud SQL Instance
        and returns a dictionary containing the IP addresses and certificate
        authority of the Cloud SQL Instance.

        :type service: googleapiclient.discovery.Resource
        :param service:
            A service object created from the Google Python API client library.
            Must be using the SQL Admin API. For more info check out
            https://github.com/googleapis/google-api-python-client.

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
            not isinstance(service, googleapiclient.discovery.Resource)
            or not isinstance(project, str)
            or not isinstance(instance, str)
        ):
            raise TypeError(
                "Arguments must be as follows: "
                + "service (googleapiclient.discovery.Resource), "
                + "proj_name (str) and inst_name (str)."
            )

        req = service.instances().get(project=project, instance=instance)
        res = req.execute()

        # Extract server certificate authority
        serverCaCert = res["serverCaCert"]["cert"]

        # Map IP addresses to type.
        ip_map = {ip["type"]: ip["ipAddress"] for ip in res["ipAddresses"]}

        metadata = {"ip_addresses": ip_map, "server_ca_cert": serverCaCert}

        return metadata

    def _get_ephemeral(service, project, instance, pub_key):
        """Requests an ephemeral certificate from the Cloud SQL Instance.

        Args:
            service (googleapiclient.discovery.Resource): A service object
              created from the Google Python API client library. Must be
              using the SQL Admin API. For more info check out
              https://github.com/googleapis/google-api-python-client.
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
            not isinstance(service, googleapiclient.discovery.Resource)
            or not isinstance(project, str)
            or not isinstance(instance, str)
            or not isinstance(pub_key, str)
        ):
            raise TypeError("Cannot take None as an argument.")

        # TODO(ryachen@) Add checks to ensure service object is valid.

        request = service.sslCerts().createEphemeral(
            project=project, instance=instance, body={"public_key": pub_key}
        )
        response = request.execute()

        return response["cert"]

    def _auth_init(self):
        """Creates and assigns a Google Python API service object for
        Google Cloud SQL Admin API.
        """

        credentials, project = google.auth.default()
        scoped_credentials = credentials.with_scopes(
            [
                "https://www.googleapis.com/auth/sqlservice.admin",
                "https://www.googleapis.com/auth.cloud-platform",
            ]
        )

        cloudsql = googleapiclient.discovery.build(
            "sqladmin", "v1beta4", credentials=scoped_credentials
        )

        self._credentials = credentials
        self._cloud_sql_service = cloudsql
