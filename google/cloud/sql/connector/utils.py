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
import tempfile

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


async def generate_keys() -> tuple[bytes, str]:
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


class AsyncTemporaryDirectory:
    """Async context manager wrapper around tempfile.TemporaryDirectory."""

    async def __aenter__(self) -> str:
        self.temp_dir = await asyncio.to_thread(tempfile.TemporaryDirectory)
        return self.temp_dir.name

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await asyncio.to_thread(self.temp_dir.cleanup)


def _write_files(
    ca_filename: str,
    serverCaCert: str,
    cert_filename: str,
    ephemeralCert: str,
    key_filename: str,
    priv_key: bytes,
) -> None:
    with open(ca_filename, "w+") as ca_out:
        ca_out.write(serverCaCert)
    with open(cert_filename, "w+") as ephemeral_out:
        ephemeral_out.write(ephemeralCert)
    with open(key_filename, "wb") as priv_out:
        priv_out.write(priv_key)


async def write_to_file(
    dir_path: str, serverCaCert: str, ephemeralCert: str, priv_key: bytes
) -> tuple[str, str, str]:
    """
    Helper function to write the serverCaCert, ephemeral certificate and
    private key to .pem files in a given directory
    """
    ca_filename = f"{dir_path}/ca.pem"
    cert_filename = f"{dir_path}/cert.pem"
    key_filename = f"{dir_path}/priv.pem"

    await asyncio.to_thread(
        _write_files,
        ca_filename,
        serverCaCert,
        cert_filename,
        ephemeralCert,
        key_filename,
        priv_key,
    )

    return (ca_filename, cert_filename, key_filename)


def format_database_user(database_version: str, user: str) -> str:
    """Format database `user` param for Cloud SQL automatic IAM authentication.

    Args:
        database_version (str): Cloud SQL database version.
        user (str): Database username to connect to Cloud SQL database with.

    Returns:
        str: Formatted database username.
    """
    # remove suffix for Postgres service accounts
    if database_version.startswith("POSTGRES"):
        suffix = ".gserviceaccount.com"
        user = user.removesuffix(suffix)
        return user

    # remove everything after and including the @ for MySQL
    if database_version.startswith("MYSQL") and "@" in user:
        return user.split("@")[0]

    return user
