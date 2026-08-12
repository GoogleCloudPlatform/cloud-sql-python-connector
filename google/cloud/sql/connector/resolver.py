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

import re
from typing import Any

import dns.asyncresolver

from google.cloud.sql.connector.connection_name import _is_valid_domain
from google.cloud.sql.connector.connection_name import _parse_connection_name
from google.cloud.sql.connector.connection_name import (
    _parse_connection_name_with_domain_name,
)
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import DnsLoopError
from google.cloud.sql.connector.exceptions import DnsResolutionError

# ^([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])

INSTANCE_DNS_NAME_PATTERN = re.compile(
    r"^([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])\.(sql|sql-psa|sql-psc)\.goog\.?$"
)

GLOBAL_INSTANCE_DNS_PATTERN = re.compile(r"\.global\.sql(-\w+)?\.goog\.?$")


def is_instance_dns_name(name: str) -> bool:
    lower = name.lower()
    return bool(
        INSTANCE_DNS_NAME_PATTERN.search(lower)
        and not GLOBAL_INSTANCE_DNS_PATTERN.search(lower)
    )


class DefaultResolver:
    """DefaultResolver simply validates and parses instance connection name."""

    def __init__(self, *args: Any, client: Any | None = None, **kwargs: Any) -> None:
        pass

    async def resolve(self, connection_name: str) -> ConnectionName:
        return _parse_connection_name(connection_name)


class DnsResolver(dns.asyncresolver.Resolver):
    """
    DnsResolver resolves domain names into instance connection names using
    TXT records in DNS.
    """

    def __init__(self, *args: Any, client: Any | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._client = client

    async def resolve(self, dns: str) -> ConnectionName:  # type: ignore
        current = dns
        visited = {current}

        # Max 10 iterations to prevent infinite CNAME loops
        for _ in range(10):
            try:
                domain_val = dns if current != dns else ""
                conn_name = _parse_connection_name_with_domain_name(
                    current, domain_val
                )
                return conn_name
            except ValueError:
                pass

            dns_normalized = current.rstrip(".")
            match = INSTANCE_DNS_NAME_PATTERN.match(dns_normalized.lower())
            if match:
                region = match.group(3)
                if region != "global":
                    if self._client is None:
                        raise ValueError(
                            "SQLAdmin client is not configured in the resolver."
                        )

                    dns_name_with_dot = dns_normalized + "."
                    resp = await self._client.resolve_connect_settings(
                        dns_name_with_dot, region
                    )
                    resolved_conn_name = resp["connectionName"]
                    return _parse_connection_name_with_domain_name(
                        resolved_conn_name, dns
                    )

            if not _is_valid_domain(current):
                raise ValueError(
                    "Arg `instance_connection_string` must have "
                    "format: PROJECT:REGION:INSTANCE or be a valid DNS domain "
                    f"name, got {dns}."
                )

            cname_found = False
            try:
                cname = await self.resolve_cname(current)
                cname_found = True
            except DnsResolutionError:
                pass

            if cname_found:
                if cname in visited:
                    raise DnsLoopError(f"CNAME loop detected for `{dns}`")
                visited.add(cname)
                current = cname
                continue

            try:
                rdata = await self.resolve_txt(current)
            except DnsResolutionError as e:
                raise DnsResolutionError(
                    f"Unable to resolve TXT record for `{dns}`"
                ) from e

            rdata.sort()
            for record in rdata:
                try:
                    conn_name = _parse_connection_name_with_domain_name(
                        record, dns
                    )
                    return conn_name
                except Exception:  # noqa: BLE001, S112
                    continue

            raise DnsResolutionError(
                f"Unable to parse TXT record for `{current}` -> `{rdata[0]}`"
                if rdata
                else f"Unable to resolve TXT record for `{current}`"
            )

        raise DnsLoopError(
            f"CNAME loop detected or max resolution depth reached for `{dns}`"
        )

    async def resolve_cname(self, dns: str) -> str:
        try:
            answers = await super().resolve(dns, "CNAME", raise_on_no_answer=True)
            return str(answers[0].target).rstrip(".")
        except Exception as e:
            raise DnsResolutionError(
                f"Unable to resolve CNAME record for `{dns}`"
            ) from e

    async def resolve_txt(self, dns: str) -> list[str]:
        try:
            answers = await super().resolve(dns, "TXT", raise_on_no_answer=True)
            return [record.to_text().strip('"') for record in answers]
        except Exception as e:
            raise DnsResolutionError(
                f"Unable to resolve TXT record for `{dns}`"
            ) from e

    async def resolve_a_record(self, dns: str) -> list[str]:
        try:
            records = await super().resolve(dns, "A", raise_on_no_answer=True)
            return [record.to_text() for record in records]
        except Exception:  # noqa: BLE001
            return []
