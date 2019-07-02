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


def get_metadata(service, project, instance):
    """
    A helper function that requests metadata from the Cloud SQL Instance
    and returns a dictionary containing the IP addresses and certificate
    authority of the Cloud SQL Instance.

    Args:
        service (googleapiclient.discovery.Resource): A service object created
          from the Google Python API client library. Must be using the SQL
          Admin API. For more info check out
          https://github.com/googleapis/google-api-python-client.
        proj_name (str): A string representing the name of the project.
        inst_name(str): A string representing the name of the instance.

    Returns:
        Returns a dictionary containing a dictionary of all IP addresses and
        their type and a string representing the certificate authority.

    Raises:
        TypeError: If any of the arguments are not the specified type.
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


def get_ephemeral(service, project, instance, pub_key):
    """
    A helper function that requests an ephemeral certificate from the
    Cloud SQL Instance.

    Args:
        service (googleapiclient.discovery.Resource): A service object created
          from the Google Python API client library. Must be using the SQL
          Admin API. For more info check out
          https://github.com/googleapis/google-api-python-client.
        project (str): A string representing the name of the project.
        instance (str): A string representing the name of the instance.
        pub_key (str): A string representing PEM-encoded RSA public key.

    Returns:
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
