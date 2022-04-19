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

import json
import ssl
from tempfile import TemporaryDirectory
from typing import Any, Dict, Tuple
from google.cloud.sql.connector import IPTypes
from google.cloud.sql.connector.instance import InstanceMetadata
from google.cloud.sql.connector.utils import write_to_file
import datetime
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes


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


async def mock_get_metadata(server_ca_cert: str, ip_address: str = "0.0.0.0") -> Dict:
    """Mock of refresh_utils.py's _get_metadata"""
    return {"ip_addresses": {"PRIMARY": ip_address}, "server_ca_cert": server_ca_cert}


async def mock_get_ephemeral(ephemeral_cert: str) -> str:
    """Mock of refresh_utils.py's _get_ephemeral_cert"""
    return ephemeral_cert


class FakeClientSessionGet:
    """Helper class to return mock data for get request."""

    async def text(self) -> str:
        response = {
            "kind": "sql#connectSettings",
            "serverCaCert": {
                "kind": "sql#sslCert",
                "certSerialNumber": "0",
                "cert": "-----BEGIN CERTIFICATE-----\nabc123\n-----END CERTIFICATE-----",
                "commonName": "Google",
                "sha1Fingerprint": "abc",
                "instance": "my-instance",
                "createTime": "2021-10-18T18:48:03.785Z",
                "expirationTime": "2031-10-16T18:49:03.785Z",
            },
            "ipAddresses": [
                {"type": "PRIMARY", "ipAddress": "0.0.0.0"},
                {"type": "PRIVATE", "ipAddress": "1.0.0.0"},
            ],
            "region": "my-region",
            "databaseVersion": "MYSQL_8_0",
            "backendType": "SECOND_GEN",
        }
        return json.dumps(response)


class FakeClientSessionPost:
    """Helper class to return mock data for post request."""

    async def text(self) -> str:
        response = {
            "ephemeralCert": {
                "kind": "sql#sslCert",
                "certSerialNumber": "",
                "cert": "-----BEGIN CERTIFICATE-----\nabc123\n-----END CERTIFICATE-----",
            }
        }
        return json.dumps(response)


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
            x509.NameAttribute(NameOID.COMMON_NAME, "{}".format(common_name)),
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
            + datetime.timedelta(minutes=10)
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
        .not_valid_after(cert._not_valid_after)
    )
    return (
        cert.sign(priv_key, hashes.SHA256(), default_backend())
        .public_bytes(encoding=serialization.Encoding.PEM)
        .decode("UTF-8")
    )


async def get_keys() -> Tuple[bytes, rsa.RSAPublicKey]:
    """
    Generate private and public key pair for testing.
    """
    private_key_obj = rsa.generate_private_key(
        backend=default_backend(), public_exponent=65537, key_size=2048
    )

    pub_key = private_key_obj.public_key()

    priv_key = private_key_obj.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return priv_key, pub_key


async def create_ssl_context() -> ssl.SSLContext:
    """Helper method to build an ssl.SSLContext for tests"""
    # generate keys and certs for test
    cert, private_key = generate_cert("my-project", "my-instance")
    server_ca_cert = self_signed_cert(cert, private_key)
    client_private, client_key = await get_keys()
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
