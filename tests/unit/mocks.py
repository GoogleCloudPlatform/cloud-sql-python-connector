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
from typing import Any, Callable, Dict, Optional, Tuple

from aiohttp import web
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth.credentials import Credentials

from google.cloud.sql.connector.connector import _DEFAULT_UNIVERSE_DOMAIN
from google.cloud.sql.connector.instance import ConnectionInfo
from google.cloud.sql.connector.utils import generate_keys
from google.cloud.sql.connector.utils import write_to_file


class FakeCredentials:
    def __init__(
        self, token: Optional[str] = None, expiry: Optional[datetime.datetime] = None
    ) -> None:
        self.token = token
        self.expiry = expiry
        self._universe_domain = _DEFAULT_UNIVERSE_DOMAIN

    @property
    def __class__(self) -> Credentials:
        # set class type to google auth Credentials
        return Credentials

    def refresh(self, request: Callable) -> None:
        """Refreshes the access token."""
        self.token = "12345"
        self.expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=60
        )

    @property
    def expired(self) -> bool:
        """Checks if the credentials are expired.

        Note that credentials can be invalid but not expired because
        Credentials with expiry set to None are considered to never
        expire.
        """
        if self.expiry is None:
            return False
        if self.expiry > datetime.datetime.now(datetime.timezone.utc):
            return False
        return True

    @property
    def universe_domain(self) -> str:
        """The universe domain value."""
        return self._universe_domain

    @property
    def valid(self) -> bool:
        """Checks the validity of the credentials.

        This is True if the credentials have a token and the token
        is not expired.
        """
        return self.token is not None and not self.expired


class BadRefresh(Exception):
    pass


class MockMetadata(ConnectionInfo):
    """Mock class for ConnectionInfo"""

    def __init__(
        self, expiration: datetime.datetime, ip_addrs: Dict = {"PRIMARY": "0.0.0.0"}
    ) -> None:
        self.expiration = expiration
        self.ip_addrs = ip_addrs


async def instance_metadata_success(*args: Any, **kwargs: Any) -> MockMetadata:
    return MockMetadata(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    )


async def instance_metadata_expired(*args: Any, **kwargs: Any) -> MockMetadata:
    return MockMetadata(
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
    )


async def instance_metadata_error(*args: Any, **kwargs: Any) -> None:
    raise BadRefresh("something went wrong...")


def generate_cert(
    project: str,
    name: str,
    cert_before: datetime.datetime = datetime.datetime.now(datetime.timezone.utc),
    cert_after: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
    + datetime.timedelta(hours=1),
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
        .not_valid_before(cert_before)
        .not_valid_after(cert_after)
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
        .not_valid_before(cert._not_valid_before)
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
    """Fake Cloud SQL instance to use for testing"""

    def __init__(
        self,
        project: str = "test-project",
        region: str = "test-region",
        name: str = "test-instance",
        db_version: str = "POSTGRES_15",
        ip_addrs: Dict = {
            "PRIMARY": "127.0.0.1",
            "PRIVATE": "10.0.0.1",
        },
        cert_before: datetime = datetime.datetime.now(datetime.timezone.utc),
        cert_expiry: datetime = datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=1),
    ) -> None:
        self.project = project
        self.region = region
        self.name = name
        self.db_version = db_version
        self.ip_addrs = ip_addrs
        self.cert_before = cert_before
        self.cert_expiry = cert_expiry
        # create self signed CA cert
        self.server_ca, self.server_key = generate_cert(
            self.project, self.name, cert_before, cert_expiry
        )
        self.server_cert = self.server_ca.sign(self.server_key, hashes.SHA256())
        self.server_cert_pem = self.server_cert.public_bytes(
            encoding=serialization.Encoding.PEM
        ).decode("UTF-8")

    async def connect_settings(self, request: Any) -> web.Response:
        ip_addrs = [{"type": k, "ipAddress": v} for k, v in self.ip_addrs.items()]
        response = {
            "kind": "sql#connectSettings",
            "serverCaCert": {
                "cert": self.server_cert_pem,
                "instance": self.name,
                "expirationTime": str(self.server_cert.not_valid_after_utc),
            },
            "dnsName": "abcde.12345.us-central1.sql.goog",
            "ipAddresses": ip_addrs,
            "region": self.region,
            "databaseVersion": self.db_version,
        }
        return web.Response(content_type="application/json", body=json.dumps(response))

    async def generate_ephemeral(self, request: Any) -> web.Response:
        body = await request.json()
        pub_key = body["public_key"]
        client_key: rsa.RSAPublicKey = serialization.load_pem_public_key(
            pub_key.encode("UTF-8"), default_backend()
        )  # type: ignore
        ephemeral_cert = client_key_signed_cert(
            self.server_ca, self.server_key, client_key
        )
        response = {
            "ephemeralCert": {
                "kind": "sql#sslCert",
                "cert": ephemeral_cert,
                "expirationTime": str(self.server_cert.not_valid_after_utc),
            }
        }
        return web.Response(content_type="application/json", body=json.dumps(response))
