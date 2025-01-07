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

from __future__ import annotations

from enum import Enum

from google.cloud.sql.connector.exceptions import IncompatibleDriverError


# TODO: Replace Enum with StrEnum when Python 3.11 is minimum supported version
class RefreshStrategy(Enum):
    LAZY = "LAZY"
    BACKGROUND = "BACKGROUND"

    @classmethod
    def _missing_(cls, value: object) -> None:
        raise ValueError(
            f"Incorrect value for refresh_strategy, got '{value}'. Want one of: "
            f"{', '.join([repr(m.value) for m in cls])}."
        )

    @classmethod
    def _from_str(cls, refresh_strategy: str) -> RefreshStrategy:
        """Convert refresh strategy from a str into RefreshStrategy."""
        return cls(refresh_strategy.upper())


class IPTypes(Enum):
    PUBLIC = "PRIMARY"
    PRIVATE = "PRIVATE"
    PSC = "PSC"

    @classmethod
    def _missing_(cls, value: object) -> None:
        raise ValueError(
            f"Incorrect value for ip_type, got '{value}'. Want one of: "
            f"{', '.join([repr(m.value) for m in cls])}, 'PUBLIC'."
        )

    @classmethod
    def _from_str(cls, ip_type_str: str) -> IPTypes:
        """Convert IP type from a str into IPTypes."""
        if ip_type_str.upper() == "PUBLIC":
            ip_type_str = "PRIMARY"
        return cls(ip_type_str.upper())


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
