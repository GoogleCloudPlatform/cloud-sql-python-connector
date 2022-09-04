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

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from typing import Tuple, Any


async def generate_keys() -> Tuple[bytes, str]:
    """A helper function to generate the private and public keys.

    backend - The value specified is default_backend(). This is because the
    cryptography library used to support different backends, but now only uses
    the default_backend().

    public_exponent - The public exponent is one of the variables used in the
    generation of the keys. 65537 is recommended due to being a good balance
    between speed and security.

    key_size - The cryptography documentation recommended a key_size
    of at least 2048.

    """
    private_key_obj = rsa.generate_private_key(
        backend=default_backend(), public_exponent=65537, key_size=2048
    )

    pub_key = (
        private_key_obj.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("UTF-8")
    )

    priv_key = private_key_obj.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return priv_key, pub_key


def write_to_file(
    dir_path: str, serverCaCert: str, ephemeralCert: str, priv_key: bytes
) -> Tuple[str, str, str]:
    """
    Helper function to write the serverCaCert, ephemeral certificate and
    private key to .pem files in a given directory
    """
    ca_filename = f"{dir_path}/ca.pem"
    cert_filename = f"{dir_path}/cert.pem"
    key_filename = f"{dir_path}/priv.pem"

    with open(ca_filename, "w+") as ca_out:
        ca_out.write(serverCaCert)
    with open(cert_filename, "w+") as ephemeral_out:
        ephemeral_out.write(ephemeralCert)
    with open(key_filename, "wb") as priv_out:
        priv_out.write(priv_key)

    return (ca_filename, cert_filename, key_filename)


class InvalidPostgresDatabaseUser(Exception):
    pass


class InvalidMySQLDatabaseUser(Exception):
    pass


def remove_suffix(input_string: str, suffix: str):
    """Remove suffix from input string if exists, else return string as is."""
    if suffix and input_string.endswith(suffix):
        return input_string[: -len(suffix)]
    return input_string


def validate_database_user(database_version: str, user: str) -> None:
    """
    Validate if `user` param is properly formatted username for given database.

    :type database_version: str
    :param database_version
        Cloud SQL database version. (i.e. POSTGRES_14, MYSQL8_0, etc.)

    :type user: str
    :param user
        Database username to connect to Cloud SQL database with.
    """
    if database_version.startswith("POSTGRES") and user.endswith(
        ".gserviceaccount.com"
    ):
        formatted_user = remove_suffix(user, ".gserviceaccount.com")
        raise InvalidPostgresDatabaseUser(
            "Improperly formatted `user` argument. Postgres IAM service account "
            "database users should have their '.gserviceaccount.com' suffix "
            f"removed. Got '{user}', try '{formatted_user}' instead."
        )

    elif database_version.startswith("MYSQL") and "@" in user:
        formatted_user = user.split("@")[0]
        raise InvalidMySQLDatabaseUser(
            "Improperly formatted `user` argument. MySQL IAM database users are "
            "truncated as follows: (IAM user: test-user@test.com -> test-user, "
            "IAM service account: account@project.iam.gserviceaccount -> account)."
            f" Got '{user}', try '{formatted_user}' instead."
        )
