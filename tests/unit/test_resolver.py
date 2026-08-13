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

from unittest.mock import AsyncMock
from unittest.mock import patch

import dns.message
import dns.rdataclass
import dns.rdatatype
import dns.resolver
import pytest

from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import DnsResolutionError
from google.cloud.sql.connector.resolver import DefaultResolver
from google.cloud.sql.connector.resolver import DnsResolver

conn_str = "my-project:my-region:my-instance"
conn_name = ConnectionName("my-project", "my-region", "my-instance")
conn_name_with_domain = ConnectionName(
    "my-project", "my-region", "my-instance", "db.example.com"
)


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


query_text = """id 1234
opcode QUERY
rcode NOERROR
flags QR AA RD RA
;QUESTION
db.example.com. IN TXT
;ANSWER
db.example.com. 0 IN TXT "test-project:test-region:test-instance"
db.example.com. 0 IN TXT "my-project:my-region:my-instance"
;AUTHORITY
;ADDITIONAL
"""


async def test_DnsResolver_with_dns_name() -> None:
    """Test DnsResolver resolves TXT record into proper instance connection name.

    Should sort valid TXT records alphabetically and take first one.
    """
    # Patch DNS resolution with valid TXT records
    with patch("dns.asyncresolver.Resolver.resolve") as mock_connect:
        answer = dns.resolver.Answer(
            "db.example.com",
            dns.rdatatype.TXT,
            dns.rdataclass.IN,
            dns.message.from_text(query_text),
        )
        mock_connect.return_value = answer
        resolver = DnsResolver()
        resolver.port = 5053
        # Resolution should return first value sorted alphabetically
        result = await resolver.resolve("db.example.com")
        assert result == conn_name_with_domain


query_text_malformed = """id 1234
opcode QUERY
rcode NOERROR
flags QR AA RD RA
;QUESTION
bad.example.com. IN TXT
;ANSWER
bad.example.com. 0 IN TXT "malformed-instance-name"
;AUTHORITY
;ADDITIONAL
"""


async def test_DnsResolver_with_malformed_txt() -> None:
    """Test DnsResolver with TXT record that holds malformed instance connection name.

    Should throw DnsResolutionError
    """
    # patch DNS resolution with malformed TXT record
    with patch("dns.asyncresolver.Resolver.resolve") as mock_connect:
        answer = dns.resolver.Answer(
            "bad.example.com",
            dns.rdatatype.TXT,
            dns.rdataclass.IN,
            dns.message.from_text(query_text_malformed),
        )
        mock_connect.return_value = answer
        resolver = DnsResolver()
        resolver.port = 5053
        with pytest.raises(DnsResolutionError) as exc_info:
            await resolver.resolve("bad.example.com")
            assert (
                exc_info.value.args[0]
                == "Unable to parse TXT record for `bad.example.com` -> `malformed-instance-name`"
            )


async def test_DnsResolver_with_bad_dns_name() -> None:
    """Test DnsResolver with bad dns name.

    Should throw DnsResolutionError
    """
    resolver = DnsResolver()
    resolver.port = 5053
    # set lifetime to 1 second for shorter timeout
    resolver.lifetime = 1
    with pytest.raises(DnsResolutionError) as exc_info:
        await resolver.resolve("bad.dns.com")
    assert exc_info.value.args[0] == "Unable to resolve TXT record for `bad.dns.com`"


a_record_query_text = """id 1234
opcode QUERY
rcode NOERROR
flags QR AA RD RA
;QUESTION
db.example.com. IN A
;ANSWER
db.example.com. 0 IN A 127.0.0.1
;AUTHORITY
;ADDITIONAL
"""


async def test_DnsResolver_resolve_a_record() -> None:
    """Test DnsResolver resolves A record into IP address."""
    with patch("dns.asyncresolver.Resolver.resolve") as mock_resolve:
        answer = dns.resolver.Answer(
            "db.example.com",
            dns.rdatatype.A,
            dns.rdataclass.IN,
            dns.message.from_text(a_record_query_text),
        )
        mock_resolve.return_value = answer
        resolver = DnsResolver()
        result = await resolver.resolve_a_record("db.example.com")
        assert result == ["127.0.0.1"]


async def test_DnsResolver_resolve_a_record_empty() -> None:
    """Test DnsResolver resolves A record but gets error."""
    with patch("dns.asyncresolver.Resolver.resolve") as mock_resolve:
        mock_resolve.side_effect = Exception("DNS Error")
        resolver = DnsResolver()
        result = await resolver.resolve_a_record("db.example.com")
        assert result == []



async def test_DnsResolver_with_direct_psc_dns_name() -> None:
    """Test DnsResolver resolves direct PSC DNS name using resolve_connect_settings."""
    dns_name = "0123456789ab.fedcba9876543.europe-north2.sql-psc.goog"
    real_conn_name = ConnectionName(
        "my-project", "europe-north2", "my-instance", dns_name
    )

    mock_client = AsyncMock()
    mock_client.resolve_connect_settings.return_value = {
        "connectionName": "my-project:europe-north2:my-instance"
    }

    resolver = DnsResolver(client=mock_client)

    result = await resolver.resolve(dns_name)

    assert result == real_conn_name
    # Verify mock_client was called with correct trailing dot DNS name!
    mock_client.resolve_connect_settings.assert_awaited_once_with(
        dns_name + ".", "europe-north2"
    )


async def test_DnsResolver_with_direct_psc_dns_name_permissive() -> None:
    """Test DnsResolver resolves direct PSC DNS name with permissive formatting."""
    dns_name = "g123.p.uscentral.sql-psc.goog"
    real_conn_name = ConnectionName(
        "my-project", "uscentral", "my-instance", dns_name
    )

    mock_client = AsyncMock()
    mock_client.resolve_connect_settings.return_value = {
        "connectionName": "my-project:uscentral:my-instance"
    }

    resolver = DnsResolver(client=mock_client)

    result = await resolver.resolve(dns_name)

    assert result == real_conn_name
    mock_client.resolve_connect_settings.assert_awaited_once_with(
        dns_name + ".", "uscentral"
    )



async def test_DnsResolver_with_cname_resolving_to_psc_dns_name() -> None:
    """Test DnsResolver resolves CNAME to PSC DNS and returns proper connection name."""
    dns_name = "db.example.com"
    cname_target = "0123456789ab.fedcba9876543.europe-north2.sql-psc.goog"
    real_conn_name = ConnectionName(
        "my-project", "europe-north2", "my-instance", dns_name
    )

    mock_client = AsyncMock()
    mock_client.resolve_connect_settings.return_value = {
        "connectionName": "my-project:europe-north2:my-instance"
    }

    resolver = DnsResolver(client=mock_client)

    # Patch resolver CNAME and TXT methods
    with patch.object(
        resolver, "resolve_cname", AsyncMock(return_value=cname_target)
    ), patch.object(
        resolver, "resolve_txt", AsyncMock(side_effect=Exception("No TXT"))
    ):

        result = await resolver.resolve(dns_name)

    assert result == real_conn_name
    mock_client.resolve_connect_settings.assert_awaited_once_with(
        cname_target + ".", "europe-north2"
    )


async def test_DnsResolver_with_recursive_cnames_to_psc_dns_name() -> None:
    """Test DnsResolver resolves recursive CNAMEs to PSC DNS successfully."""
    dns_name = "name1.example.com"
    cname2 = "name2.example.com"
    cname_target = "0123456789ab.fedcba9876543.europe-north2.sql-psc.goog"
    real_conn_name = ConnectionName(
        "my-project", "europe-north2", "my-instance", dns_name
    )

    mock_client = AsyncMock()
    mock_client.resolve_connect_settings.return_value = {
        "connectionName": "my-project:europe-north2:my-instance"
    }

    resolver = DnsResolver(client=mock_client)

    # Mock Lookup CNAME sequence
    cname_mock = AsyncMock(
        side_effect=lambda name: cname2 if name == dns_name else cname_target
    )

    with patch.object(resolver, "resolve_cname", cname_mock), patch.object(
        resolver, "resolve_txt", AsyncMock(side_effect=Exception("No TXT"))
    ):

        result = await resolver.resolve(dns_name)

    assert result == real_conn_name
    mock_client.resolve_connect_settings.assert_awaited_once_with(
        cname_target + ".", "europe-north2"
    )


async def test_DnsResolver_cname_loop_throws_error() -> None:
    """Test DnsResolver throws error if a CNAME loop is detected."""
    dns_name = "name1.example.com"
    cname2 = "name2.example.com"

    resolver = DnsResolver()

    cname_mock = AsyncMock(
        side_effect=lambda name: cname2 if name == dns_name else dns_name
    )

    with patch.object(resolver, "resolve_cname", cname_mock), patch.object(
        resolver, "resolve_txt", AsyncMock(side_effect=Exception("No TXT"))
    ):

        with pytest.raises(DnsResolutionError) as exc_info:
            await resolver.resolve(dns_name)
        assert "CNAME loop detected" in str(exc_info.value)


async def test_DnsResolver_global_region_skips_direct_resolution() -> None:
    """Test DnsResolver skips direct resolution if the PSC DNS name has a global region."""
    dns_name = "0123456789ab.fedcba9876543.global.sql-psc.goog"

    mock_client = AsyncMock()
    resolver = DnsResolver(client=mock_client)

    # Patch CNAME and TXT to fail, so it eventually raises DnsResolutionError
    with patch.object(
        resolver, "resolve_cname", AsyncMock(side_effect=DnsResolutionError("No CNAME"))
    ), patch.object(
        resolver, "resolve_txt", AsyncMock(side_effect=DnsResolutionError("No TXT"))
    ), pytest.raises(DnsResolutionError):
        await resolver.resolve(dns_name)

    # Verify mock_client was NOT called because direct resolution was skipped
    mock_client.resolve_connect_settings.assert_not_called()


async def test_DnsResolver_no_client_error() -> None:
    """Test DnsResolver throws ValueError if client is not configured for PSC DNS."""
    dns_name = "0123456789ab.fedcba9876543.europe-north2.sql-psc.goog"
    resolver = DnsResolver(client=None)
    with pytest.raises(ValueError) as exc_info:
        await resolver.resolve(dns_name)
    assert "SQLAdmin client is not configured in the resolver." in str(exc_info.value)


async def test_DnsResolver_invalid_domain() -> None:
    """Test DnsResolver throws ValueError if input is neither connection name nor valid domain."""
    resolver = DnsResolver()
    with pytest.raises(ValueError) as exc_info:
        await resolver.resolve("invalidname")
    assert "must have format: PROJECT:REGION:INSTANCE or be a valid DNS domain name" in str(exc_info.value)


async def test_DnsResolver_max_depth_reached() -> None:
    """Test DnsResolver throws DnsResolutionError if max resolution depth is reached."""
    dns_name = "name0.example.com"
    cname_map = {f"name{i}.example.com": f"name{i+1}.example.com" for i in range(10)}

    resolver = DnsResolver()

    async def mock_resolve_cname(name: str) -> str:
        if name in cname_map:
            return cname_map[name]
        raise DnsResolutionError("No CNAME")

    with patch.object(resolver, "resolve_cname", AsyncMock(side_effect=mock_resolve_cname)), patch.object(
        resolver, "resolve_txt", AsyncMock(side_effect=DnsResolutionError("No TXT"))
    ):
        with pytest.raises(DnsResolutionError) as exc_info:
            await resolver.resolve(dns_name)
        assert "max resolution depth reached" in str(exc_info.value)