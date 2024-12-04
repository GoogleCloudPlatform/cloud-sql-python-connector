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

import pytest  # noqa F401 Needed to run the tests

from google.cloud.sql.connector.connection_name import _parse_connection_name
from google.cloud.sql.connector.connection_name import ConnectionName


def test_ConnectionName() -> None:
    conn_name = ConnectionName("project", "region", "instance")
    # test class attributes are set properly
    assert conn_name.project == "project"
    assert conn_name.region == "region"
    assert conn_name.instance_name == "instance"
    assert conn_name.domain_name == ""
    # test ConnectionName str() method prints instance connection name
    assert str(conn_name) == "project:region:instance"


def test_ConnectionName_with_domain_name() -> None:
    conn_name = ConnectionName("project", "region", "instance", "db.example.com")
    # test class attributes are set properly
    assert conn_name.project == "project"
    assert conn_name.region == "region"
    assert conn_name.instance_name == "instance"
    assert conn_name.domain_name == "db.example.com"
    # test ConnectionName str() method prints with domain name
    assert str(conn_name) == "db.example.com -> project:region:instance"


@pytest.mark.parametrize(
    "connection_name, expected",
    [
        ("project:region:instance", ConnectionName("project", "region", "instance")),
        (
            "domain-prefix:project:region:instance",
            ConnectionName("domain-prefix:project", "region", "instance"),
        ),
    ],
)
def test_parse_connection_name(connection_name: str, expected: ConnectionName) -> None:
    """
    Test that _parse_connection_name works correctly on
    normal instance connection names and domain-scoped projects.
    """
    assert expected == _parse_connection_name(connection_name)


def test_parse_connection_name_bad_conn_name() -> None:
    """
    Tests that ValueError is thrown for bad instance connection names.
    """
    with pytest.raises(ValueError):
        _parse_connection_name("project:instance")  # missing region
