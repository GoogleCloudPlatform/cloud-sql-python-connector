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

from dataclasses import dataclass
import re

# Instance connection name is the format <PROJECT>:<REGION>:<INSTANCE_NAME>
# Additionally, we have to support legacy "domain-scoped" projects
# (e.g. "google.com:PROJECT")
CONN_NAME_REGEX = re.compile(("([^:]+(:[^:]+)?):([^:]+):([^:]+)"))
# The domain name pattern in accordance with RFC 1035, RFC 1123 and RFC 2181.
DOMAIN_NAME_REGEX = re.compile(
    r"^(?:[_a-z0-9](?:[_a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?)?$"
)


@dataclass
class ConnectionName:
    """ConnectionName represents a Cloud SQL instance's "instance connection name".

    Takes the format "<PROJECT>:<REGION>:<INSTANCE_NAME>".
    """

    project: str
    region: str
    instance_name: str
    domain_name: str = ""

    def __str__(self) -> str:
        if self.domain_name:
            return f"{self.domain_name} -> {self.project}:{self.region}:{self.instance_name}"
        return f"{self.project}:{self.region}:{self.instance_name}"

    def get_connection_string(self) -> str:
        """Get the instance connection string for the Cloud SQL instance."""
        return f"{self.project}:{self.region}:{self.instance_name}"


def _is_valid_domain(domain_name: str) -> bool:
    if DOMAIN_NAME_REGEX.fullmatch(domain_name) is None:
        return False
    return True


def _parse_connection_name(connection_name: str) -> ConnectionName:
    return _parse_connection_name_with_domain_name(connection_name, "")


def _parse_connection_name_with_domain_name(
    connection_name: str, domain_name: str
) -> ConnectionName:
    if CONN_NAME_REGEX.fullmatch(connection_name) is None:
        raise ValueError(
            "Arg `instance_connection_string` must have "
            "format: PROJECT:REGION:INSTANCE, "
            f"got {connection_name}."
        )
    connection_name_split = CONN_NAME_REGEX.split(connection_name)
    return ConnectionName(
        connection_name_split[1],
        connection_name_split[3],
        connection_name_split[4],
        domain_name,
    )
