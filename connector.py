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


def get_ephemeral(service, project, instance, pub_key):
    """
    A helper function that requests an ephemeral certificate from the
    Cloud SQL Instance.

    Takes in a service object, the project name, the instance name and
    a public key.

    Returns the certificate as a string.
    """

    # TODO(Write checks)

    request = service.sslCerts().createEphemeral(
        project=project,
        instance=instance,
        body={
            'public_key': pub_key
        }
    )
    response = request.execute()

    # TODO: Add check if response is error or not.

    print(response)

    return response['cert']
