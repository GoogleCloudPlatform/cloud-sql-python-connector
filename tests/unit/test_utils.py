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

from google.cloud.sql.connector import utils
from google.cloud.sql.connector.exceptions import InvalidIAMDatabaseUser

import pytest  # noqa F401 Needed to run the tests


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


def test_remove_suffix_with_suffix() -> None:
    """
    Test to check if remove_suffix returns string with suffix removed.
    """
    output = utils.remove_suffix(
        "service-account@test.iam.gserviceaccount.com", ".gserviceaccount.com"
    )
    assert output == "service-account@test.iam"


def test_remove_suffix_without_suffix() -> None:
    """
    Test to check if remove_suffix returns input string if suffix not present.
    """
    output = utils.remove_suffix("service-account@test.iam", ".gserviceaccount.com")
    assert output == "service-account@test.iam"


def test_validate_database_user_postgres() -> None:
    """
    Test that validate_database user throws no exception for properly
    formatted Postgres database users.
    """
    utils.validate_database_user("POSTGRES_14", "service-account@test.iam")
    utils.validate_database_user("POSTGRES_14", "test@test.com")


def test_validate_database_user_mysql() -> None:
    """
    Test that validate_database user throws no exception for properly
    formatted MySQL database users.
    """
    utils.validate_database_user("MYSQL_8_0", "service-account")
    utils.validate_database_user("MYSQL_8_0", "test")


def test_validate_database_user_postgres_InvalidIAMDatabaseUser() -> None:
    """
    Test that validate_database user raises exception with improperly
    formatted Postgres service account database user.
    """
    with pytest.raises(InvalidIAMDatabaseUser):
        utils.validate_database_user(
            "POSTGRES_14", "service-account@test.iam.gserviceaccount.com"
        )


def test_validate_database_user_mysql_InvalidIAMDatabaseUser() -> None:
    """
    Test that validate_database user raises exception with improperly
    formatted MySQL database user.
    """
    # test IAM service account user
    with pytest.raises(InvalidIAMDatabaseUser):
        utils.validate_database_user(
            "MYSQL_8_0", "service-account@test.iam.gserviceaccount.com"
        )
    # test IAM user
    with pytest.raises(InvalidIAMDatabaseUser):
        utils.validate_database_user("MYSQL_8_0", "test@test.com")
