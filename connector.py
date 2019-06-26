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
import os


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


def get_serverCaCert(service, project, instance):
    """
    A helper function that requests the instance metadata and extracts the IP
    address and certificate authority of the server.

    Takes in a service object, the project name and the instance name.

    Yields: The server's certificate authority as a string and saves the IP
    in the 'db_host' environment variable.
    """

    request = service.instances().get(project=project, instance=instance)
    response = request.execute()

    # Extract IP of server.
    os.environ['db_host'] = response['ipAddresses'][0]['ipAddress']

    # Extract and return cert
    serverCaCert = response['serverCaCert']['cert']
    return serverCaCert
