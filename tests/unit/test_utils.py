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

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from google.cloud.sql.connector import utils


@pytest.mark.asyncio
async def test_generate_keys_not_return_none() -> None:
    """
    Test to check if objects are being produced from the generate_keys()
    function.
    """

    res1, res2 = await utils.generate_keys()
    assert (res1 is not None) and (res2 is not None)


@pytest.mark.asyncio
async def test_generate_keys_returns_bytes_and_str() -> None:
    """
    Test to check if objects produced from the generate_keys() function are of
    the expected types.
    """

    res1, res2 = await utils.generate_keys()
    assert isinstance(res1, bytes) and (isinstance(res2, str))


@pytest.mark.asyncio
async def test_generate_keys_pkcs8_and_spki_pem_format() -> None:
    """Test that generate_keys() serializes private keys in modern PKCS#8 PEM
    format and public keys in SubjectPublicKeyInfo PEM format."""
    priv_pem, pub_pem = await utils.generate_keys()

    assert priv_pem.startswith(b"-----BEGIN PRIVATE KEY-----\n")
    assert not priv_pem.startswith(b"-----BEGIN RSA PRIVATE KEY-----\n")
    assert pub_pem.startswith("-----BEGIN PUBLIC KEY-----\n")

    priv_key = serialization.load_pem_private_key(priv_pem, password=None)
    pub_key = serialization.load_pem_public_key(pub_pem.encode("UTF-8"))
    assert isinstance(priv_key, rsa.RSAPrivateKey)
    assert isinstance(pub_key, rsa.RSAPublicKey)
    assert priv_key.public_key().public_numbers() == pub_key.public_numbers()


def test_format_database_user_postgres() -> None:
    """
    Test that format_database_user properly formats Postgres IAM database users.
    """
    service_account = utils.format_database_user(
        "POSTGRES_14", "service-account@test.iam"
    )
    service_account2 = utils.format_database_user(
        "POSTGRES_14", "service-account@test.iam.gserviceaccount.com"
    )
    assert service_account == "service-account@test.iam"
    assert service_account2 == "service-account@test.iam"
    user = utils.format_database_user("POSTGRES_14", "test@test.com")
    assert user == "test@test.com"


def test_format_database_user_mysql() -> None:
    """
    Test that format_database _user properly formats MySQL IAM database users.
    """
    service_account = utils.format_database_user(
        "MYSQL_8_0", "service-account@test.iam"
    )
    service_account2 = utils.format_database_user(
        "MYSQL_8_0", "service-account@test.iam.gserviceaccount.com"
    )
    service_account3 = utils.format_database_user("MYSQL_8_0", "service-account")
    assert service_account == "service-account"
    assert service_account2 == "service-account"
    assert service_account3 == "service-account"
    user = utils.format_database_user("MYSQL_8_0", "test@test.com")
    user2 = utils.format_database_user("MYSQL_8_0", "test")
    assert user == "test"
    assert user2 == "test"


def test_iptypes_from_str() -> None:
    """Test IPTypes._from_str parses string values properly."""
    from google.cloud.sql.connector.enums import IPTypes

    assert IPTypes._from_str("sqldata") == IPTypes.SQL_DATA
    assert IPTypes._from_str("sql_data") == IPTypes.SQL_DATA
    assert IPTypes._from_str("public") == IPTypes.PUBLIC
    assert IPTypes._from_str("private") == IPTypes.PRIVATE
    assert IPTypes._from_str("psc") == IPTypes.PSC


