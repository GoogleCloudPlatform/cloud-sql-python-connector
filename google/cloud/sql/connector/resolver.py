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

from dns.asyncresolver import Resolver

from google.cloud.sql.connector.instance import _parse_instance_connection_name


class DefaultResolver:
    """DefaultResolver simply validates and parses instance connection name."""

    async def resolve(connection_name: str) -> str:
        pass


class DnsResolver(Resolver):
    """
    DnsResolver resolves domain names into instance connection names using
    TXT records in DNS.
    """

    pass


async def resolve(dns: str) -> str:
    pass
