""""
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
import pytest  # noqa F401 Needed to run the tests

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
