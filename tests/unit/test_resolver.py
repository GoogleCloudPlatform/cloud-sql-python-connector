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

import pytest

from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import DnsResolutionError
from google.cloud.sql.connector.resolver import DefaultResolver
from google.cloud.sql.connector.resolver import DnsResolver

conn_str = "test-project:test-region:test-instance"
conn_name = ConnectionName("test-project", "test-region", "test-instance")


async def test_DefaultResolver() -> None:
    """Test DefaultResolver just parses instance connection string."""
    resolver = DefaultResolver()
    result = await resolver.resolve(conn_str)
    assert result == conn_name


async def test_DnsResolver_with_conn_str() -> None:
    """Test DnsResolver with instance connection name just parses connection string."""
    resolver = DnsResolver()
    result = await resolver.resolve(conn_str)
    assert result == conn_name


async def test_DnsResolver_with_dns_name() -> None:
    """Test DnsResolver resolves TXT record into proper instance connection name."""
    resolver = DnsResolver()
    resolver.port = 5053
    result = await resolver.resolve("db.example.com")
    assert result == conn_name


async def test_DnsResolver_with_malformed_txt() -> None:
    """Test DnsResolver with TXT record that holds malformed instance connection name.

    Should throw DnsResolutionError
    """
    resolver = DnsResolver()
    resolver.port = 5053
    with pytest.raises(DnsResolutionError) as exc_info:
        await resolver.resolve("bad.example.com")
        assert (
            exc_info.value.args[0]
            == "Unable to parse TXT record for `bad.example.com` -> `bad-instance-name`"
        )


async def test_DnsResolver_with_bad_dns_name() -> None:
    """Test DnsResolver with bad dns name.

    Should throw DnsResolutionError
    """
    resolver = DnsResolver()
    resolver.port = 5053
    with pytest.raises(DnsResolutionError) as exc_info:
        await resolver.resolve("bad.dns.com")
    assert exc_info.value.args[0] == "Unable to resolve TXT record for `bad.dns.com`"