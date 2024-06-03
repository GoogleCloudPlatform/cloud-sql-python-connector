# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from enum import Enum

from google.cloud.sql.connector.exceptions import IncompatibleDriverError


class DriverMapping(Enum):
    """Maps a given database driver to it's corresponding database engine."""

    ASYNCPG = "POSTGRES"
    PG8000 = "POSTGRES"
    PYMYSQL = "MYSQL"
    PYTDS = "SQLSERVER"

    @staticmethod
    def validate_engine(driver: str, engine_version: str) -> None:
        """Validate that the given driver is compatible with the given engine.

        Args:
            driver (str): Database driver being used. (i.e. "pg8000")
            engine_version (str): Database engine version. (i.e. "POSTGRES_16")

        Raises:
            IncompatibleDriverError: If the given driver is not compatible with
                the given engine.
        """
        mapping = DriverMapping[driver.upper()]
        if not engine_version.startswith(mapping.value):
            raise IncompatibleDriverError(
                f"Database driver '{driver}' is incompatible with database "
                f"version '{engine_version}'. Given driver can "
                f"only be used with Cloud SQL {mapping.value} databases."
            )
