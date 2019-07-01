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
import googleapiclient


def get_ephemeral(service, project, instance, pub_key):
    """
    A helper function that requests an ephemeral certificate from the
    Cloud SQL Instance.

    Takes in a service object, the project name, the instance name and
    a public key.

    Yields: The certificate as a string.
    """

    if (
        service is None or
        project is None or
        instance is None or
        pub_key is None
    ):
        print("Cannot take None as an argument.")
        exit()

    # TODO(ryachen@) Add checks to ensure service object is valid.

    request = service.sslCerts().createEphemeral(
        project=project,
        instance=instance,
        body={
            'public_key': pub_key
        }
    )
    response = request.execute()

    # TODO: Add check if response is error or not.

    return response['cert']


def get_serverCaCert(service, project_name, instance_name):
    """
    A helper function that requests the instance metadata and extracts the IP
    address and certificate authority of the server.

    Arguments:
        service (googleapiclient.discovery.Resource): A service object created
            from the Google Python API client library. Must be using the SQL
            Admin API.
        project_name (str): A string representing the name of the project.
        instance_name (str): A string representing the name of the instance.
            Usually found in environment variable 'CLOUD_SQL_INSTANCE_NAME.'

    Returns:
        A string representing the serverCaCert and another string representing
        the IP address of the Cloud SQL instance.

    Raises:
        TypeError: If one or more arguments passed in do not match the
            required type.
    """

    if (
        not isinstance(service, googleapiclient.discovery.Resource) or
        not isinstance(project_name, str) or
        not isinstance(instance_name, str)
    ):
        raise TypeError(
            "Arguments must be as follows: " +
            "service (googleapiclient.discover.Resource), project_name (str)" +
            " and instance_name (str)."
        )

    # Create request and execute request to receive response.
    request = service.instances().get(
        project=project_name,
        instance=instance_name
    )

    response = request.execute()

    # Extract IP of server.
    ipAddr = response['ipAddresses'][0]['ipAddress']

    # Extract server certificate authority.
    serverCaCert = response['serverCaCert']['cert']

    return serverCaCert, ipAddr
