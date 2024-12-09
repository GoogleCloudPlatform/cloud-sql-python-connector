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

import dns.asyncresolver

from google.cloud.sql.connector.connection_name import (
    _parse_connection_name_with_domain_name,
)
from google.cloud.sql.connector.connection_name import _parse_connection_name
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import DnsResolutionError


class DefaultResolver:
    """DefaultResolver simply validates and parses instance connection name."""

    async def resolve(self, connection_name: str) -> ConnectionName:
        return _parse_connection_name(connection_name)


class DnsResolver(dns.asyncresolver.Resolver):
    """
    DnsResolver resolves domain names into instance connection names using
    TXT records in DNS.
    """

    async def resolve(self, dns: str) -> ConnectionName:  # type: ignore
        try:
            conn_name = _parse_connection_name(dns)
        except ValueError:
            # The connection name was not project:region:instance format.
            # Attempt to query a TXT record to get connection name.
            conn_name = await self.query_dns(dns)
        return conn_name

    async def query_dns(self, dns: str) -> ConnectionName:
        try:
            # Attempt to query the TXT records.
            records = await super().resolve(dns, "TXT", raise_on_no_answer=True)
            # Sort the TXT record values alphabetically, strip quotes as record
            # values can be returned as raw strings
            rdata = [record.to_text().strip('"') for record in records]
            rdata.sort()
            # Attempt to parse records, returning the first valid record.
            for record in rdata:
                try:
                    conn_name = _parse_connection_name_with_domain_name(record, dns)
                    return conn_name
                except Exception:
                    continue
            # If all records failed to parse, throw error
            raise DnsResolutionError(
                f"Unable to parse TXT record for `{dns}` -> `{rdata[0]}`"
            )
        # Don't override above DnsResolutionError
        except DnsResolutionError:
            raise
        except Exception as e:
            raise DnsResolutionError(f"Unable to resolve TXT record for `{dns}`") from e
