""""
Copyright 2022 Google LLC

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
# file containing all mocks used for Cloud SQL Python Connector unit tests

import datetime
import json
import ssl
from tempfile import TemporaryDirectory
from typing import Any, Dict, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from google.cloud.sql.connector import IPTypes
from google.cloud.sql.connector.instance import InstanceMetadata
from google.cloud.sql.connector.utils import generate_keys, write_to_file


class MockInstance:
    _enable_iam_auth: bool

    def __init__(
        self,
        enable_iam_auth: bool = False,
    ) -> None:
        self._enable_iam_auth = enable_iam_auth

    # mock connect_info
    async def connect_info(
        self,
        driver: str,
        ip_type: IPTypes,
        **kwargs: Any,
    ) -> Any:
        return True


class BadRefresh(Exception):
    pass


class MockMetadata(InstanceMetadata):
    """Mock class for InstanceMetadata"""

    def __init__(
        self, expiration: datetime.datetime, ip_addrs: Dict = {"PRIMARY": "0.0.0.0"}
    ) -> None:
        self.expiration = expiration
        self.ip_addrs = ip_addrs


async def instance_metadata_success(*args: Any, **kwargs: Any) -> MockMetadata:
    return MockMetadata(datetime.datetime.now() + datetime.timedelta(minutes=10))


async def instance_metadata_expired(*args: Any, **kwargs: Any) -> MockMetadata:
    return MockMetadata(datetime.datetime.now() - datetime.timedelta(minutes=10))


async def instance_metadata_error(*args: Any, **kwargs: Any) -> None:
    raise BadRefresh("something went wrong...")


def generate_cert(
    project: str, name: str
) -> Tuple[x509.CertificateBuilder, rsa.RSAPrivateKey]:
    """
    Generate a private key and cert object to be used in testing.
    """
    # generate private key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    common_name = f"{project}:{name}"
    # configure cert subject
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Mountain View"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Google Inc"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    # build cert
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(
            # cert valid for 10 mins
            datetime.datetime.utcnow()
            + datetime.timedelta(minutes=60)
        )
    )
    return cert, key


def self_signed_cert(cert: x509.CertificateBuilder, key: rsa.RSAPrivateKey) -> str:
    """
    Create a PEM encoded certificate that is self-signed.
    """
    return (
        cert.sign(key, hashes.SHA256(), default_backend())
        .public_bytes(encoding=serialization.Encoding.PEM)
        .decode("UTF-8")
    )


def client_key_signed_cert(
    cert: x509.CertificateBuilder,
    priv_key: rsa.RSAPrivateKey,
    client_key: rsa.RSAPublicKey,
) -> str:
    """
    Create a PEM encoded certificate that is signed by given public key.
    """
    # configure cert subject
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Google Inc"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Google Cloud SQL Client"),
        ]
    )
    # build cert
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(client_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(cert._not_valid_after)  # type: ignore
    )
    return (
        cert.sign(priv_key, hashes.SHA256(), default_backend())
        .public_bytes(encoding=serialization.Encoding.PEM)
        .decode("UTF-8")
    )


async def create_ssl_context() -> ssl.SSLContext:
    """Helper method to build an ssl.SSLContext for tests"""
    # generate keys and certs for test
    cert, private_key = generate_cert("my-project", "my-instance")
    server_ca_cert = self_signed_cert(cert, private_key)
    client_private, client_bytes = await generate_keys()
    client_key: rsa.RSAPublicKey = serialization.load_pem_public_key(
        client_bytes.encode("UTF-8"), default_backend()
    )  # type: ignore
    ephemeral_cert = client_key_signed_cert(cert, private_key, client_key)
    # build default ssl.SSLContext
    context = ssl.create_default_context()
    # load ssl.SSLContext with certs
    with TemporaryDirectory() as tmpdir:
        ca_filename, cert_filename, key_filename = write_to_file(
            tmpdir, server_ca_cert, ephemeral_cert, client_private
        )
        context.load_cert_chain(cert_filename, keyfile=key_filename)
        context.load_verify_locations(cafile=ca_filename)
    return context


class FakeCSQLInstance:
    def __init__(
        self,
        project: str = "my-project",
        region: str = "my-region",
        name: str = "my-instance",
        db_version: str = "POSTGRES_14",
    ) -> None:
        self.project = project
        self.region = region
        self.name = name
        self.db_version = db_version
        self.ip_addrs = {"PRIMARY": "0.0.0.0", "PRIVATE": "1.1.1.1"}
        self.backend_type = "SECOND_GEN"

        # generate server private key and cert
        cert, key = generate_cert(project, name)
        self.key = key
        self.cert = cert

    def connect_settings(self, ip_addrs: Optional[Dict] = None) -> str:
        """
        Mock data for the following API:
        https://sqladmin.googleapis.com/sql/v1beta4/projects/{project}/instances/{instance}/connectSettings
        """
        server_ca_cert = self_signed_cert(self.cert, self.key)
        ip_addrs = ip_addrs if ip_addrs else self.ip_addrs
        ip_addresses = [
            {"type": key, "ipAddress": value} for key, value in ip_addrs.items()
        ]
        return json.dumps(
            {
                "kind": "sql#connectSettings",
                "serverCaCert": {
                    "cert": server_ca_cert,
                    "instance": self.name,
                    "expirationTime": str(
                        datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
                    ),
                },
                "dnsName": "abcde.12345.us-central1.sql.goog",
                "ipAddresses": ip_addresses,
                "region": self.region,
                "databaseVersion": self.db_version,
                "backendType": self.backend_type,
            }
        )

    def generate_ephemeral(self, client_bytes: str) -> str:
        """
        Mock data for the following API:
        https://sqladmin.googleapis.com/sql/v1beta4/projects/{project}/instances/{instance}:generateEphemeralCert
        """
        client_key: rsa.RSAPublicKey = serialization.load_pem_public_key(
            client_bytes.encode("UTF-8"), default_backend()
        )  # type: ignore
        ephemeral_cert = client_key_signed_cert(self.cert, self.key, client_key)
        return json.dumps(
            {
                "ephemeralCert": {
                    "kind": "sql#sslCert",
                    "cert": ephemeral_cert,
                    "expirationTime": str(
                        datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
                    ),
                }
            }
        )
