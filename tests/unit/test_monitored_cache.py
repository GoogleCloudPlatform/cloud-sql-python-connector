# Copyright 2025 Google LLC
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

import asyncio
import socket
import ssl

import dns.message
import dns.rdataclass
import dns.rdatatype
import dns.resolver
from mock import patch
import pytest

from google.cloud.sql.connector.client import CloudSQLClient
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import CacheClosedError
from google.cloud.sql.connector.lazy import LazyRefreshCache
from google.cloud.sql.connector.monitored_cache import MonitoredCache
from google.cloud.sql.connector.resolver import DefaultResolver
from google.cloud.sql.connector.resolver import DnsResolver
from google.cloud.sql.connector.utils import generate_keys

query_text = """id 1234
opcode QUERY
rcode NOERROR
flags QR AA RD RA
;QUESTION
db.example.com. IN TXT
;ANSWER
db.example.com. 0 IN TXT "test-project:test-region:test-instance"
;AUTHORITY
;ADDITIONAL
"""


async def test_MonitoredCache_properties(fake_client: CloudSQLClient) -> None:
    """
    Test that MonitoredCache properties work as expected.
    """
    conn_name = ConnectionName("test-project", "test-region", "test-instance")
    cache = LazyRefreshCache(
        conn_name,
        client=fake_client,
        keys=asyncio.create_task(generate_keys()),
        enable_iam_auth=False,
    )
    monitored_cache = MonitoredCache(cache, 30, DefaultResolver())
    # test that ticker is not set for instance not using domain name
    assert monitored_cache.domain_name_ticker is None
    # test closed property
    assert monitored_cache.closed is False
    # close cache and make sure property is updated
    await monitored_cache.close()
    assert monitored_cache.closed is True


async def test_MonitoredCache_CacheClosedError(fake_client: CloudSQLClient) -> None:
    """
    Test that MonitoredCache.connect_info errors when cache is closed.
    """
    conn_name = ConnectionName("test-project", "test-region", "test-instance")
    cache = LazyRefreshCache(
        conn_name,
        client=fake_client,
        keys=asyncio.create_task(generate_keys()),
        enable_iam_auth=False,
    )
    monitored_cache = MonitoredCache(cache, 30, DefaultResolver())
    # test closed property
    assert monitored_cache.closed is False
    # close cache and make sure property is updated
    await monitored_cache.close()
    assert monitored_cache.closed is True
    # attempt to get connect info from closed cache
    with pytest.raises(CacheClosedError):
        await monitored_cache.connect_info()


async def test_MonitoredCache_with_DnsResolver(fake_client: CloudSQLClient) -> None:
    """
    Test that MonitoredCache with DnsResolver work as expected.
    """
    conn_name = ConnectionName(
        "test-project", "test-region", "test-instance", "db.example.com"
    )
    cache = LazyRefreshCache(
        conn_name,
        client=fake_client,
        keys=asyncio.create_task(generate_keys()),
        enable_iam_auth=False,
    )
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
        monitored_cache = MonitoredCache(cache, 30, resolver)
        # test that ticker is set for instance using domain name
        assert type(monitored_cache.domain_name_ticker) is asyncio.Task
        # test closed property
        assert monitored_cache.closed is False
        # close cache and make sure property is updated
        await monitored_cache.close()
        assert monitored_cache.closed is True
        # domain name ticker should be set back to None
        assert monitored_cache.domain_name_ticker is None


async def test_MonitoredCache_with_disabled_failover(
    fake_client: CloudSQLClient,
) -> None:
    """
    Test that MonitoredCache disables DNS polling with failover_period=0
    """
    conn_name = ConnectionName(
        "test-project", "test-region", "test-instance", "db.example.com"
    )
    cache = LazyRefreshCache(
        conn_name,
        client=fake_client,
        keys=asyncio.create_task(generate_keys()),
        enable_iam_auth=False,
    )
    monitored_cache = MonitoredCache(cache, 0, DnsResolver())
    # test that ticker is not set when failover is disabled
    assert monitored_cache.domain_name_ticker is None
    # test closed property
    assert monitored_cache.closed is False
    # close cache and make sure property is updated
    await monitored_cache.close()
    assert monitored_cache.closed is True


@pytest.mark.usefixtures("proxy_server")
async def test_MonitoredCache_check_domain_name(
    context: ssl.SSLContext, fake_client: CloudSQLClient
) -> None:
    """
    Test that MonitoredCache is closed when _check_domain_name has domain change.
    """
    conn_name = ConnectionName(
        "my-project", "my-region", "my-instance", "db.example.com"
    )
    cache = LazyRefreshCache(
        conn_name,
        client=fake_client,
        keys=asyncio.create_task(generate_keys()),
        enable_iam_auth=False,
    )
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

        # configure a local socket
        ip_addr = "127.0.0.1"
        sock = context.wrap_socket(
            socket.create_connection((ip_addr, 3307)),
            server_hostname=ip_addr,
        )
        # verify socket is open
        assert sock.fileno() != -1
        # set failover to 0 to disable polling
        monitored_cache = MonitoredCache(cache, 0, resolver)
        # add socket to cache
        monitored_cache.sockets = [sock]
        # check cache is not closed
        assert monitored_cache.closed is False
        # call _check_domain_name and verify cache is closed
        await monitored_cache._check_domain_name()
        assert monitored_cache.closed is True
        # verify socket was closed
        assert sock.fileno() == -1


@pytest.mark.usefixtures("proxy_server")
async def test_MonitoredCache_purge_closed_sockets(
    context: ssl.SSLContext, fake_client: CloudSQLClient
) -> None:
    """
    Test that MonitoredCache._purge_closed_sockets removes closed sockets from
    cache.
    """
    conn_name = ConnectionName(
        "my-project", "my-region", "my-instance", "db.example.com"
    )
    cache = LazyRefreshCache(
        conn_name,
        client=fake_client,
        keys=asyncio.create_task(generate_keys()),
        enable_iam_auth=False,
    )
    # configure a local socket
    ip_addr = "127.0.0.1"
    sock = context.wrap_socket(
        socket.create_connection((ip_addr, 3307)),
        server_hostname=ip_addr,
    )

    # set failover to 0 to disable polling
    monitored_cache = MonitoredCache(cache, 0, DnsResolver())
    # verify socket is open
    assert sock.fileno() != -1
    # add socket to cache
    monitored_cache.sockets = [sock]
    # call _purge_closed_sockets and verify socket remains
    monitored_cache._purge_closed_sockets()
    # verify socket is still open
    assert sock.fileno() != -1
    assert len(monitored_cache.sockets) == 1
    # close socket
    sock.close()
    # call _purge_closed_sockets and verify socket is removed
    monitored_cache._purge_closed_sockets()
    assert len(monitored_cache.sockets) == 0
