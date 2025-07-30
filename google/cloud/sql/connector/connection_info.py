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

import abc
from dataclasses import dataclass
import logging
import ssl
from typing import Any, Optional, TYPE_CHECKING

from aiofiles.tempfile import TemporaryDirectory

from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError
from google.cloud.sql.connector.exceptions import TLSVersionError
from google.cloud.sql.connector.utils import write_to_file

if TYPE_CHECKING:
    import datetime

    from google.cloud.sql.connector.enums import IPTypes

logger = logging.getLogger(name=__name__)


class ConnectionInfoCache(abc.ABC):
    """Abstract class for Connector connection info caches."""

    @abc.abstractmethod
    async def connect_info(self) -> ConnectionInfo:
        pass

    @abc.abstractmethod
    async def force_refresh(self) -> None:
        pass

    @abc.abstractmethod
    async def close(self) -> None:
        pass

    @property
    @abc.abstractmethod
    def closed(self) -> bool:
        pass


@dataclass
class ConnectionInfo:
    """Contains all necessary information to connect securely to the
    server-side Proxy running on a Cloud SQL instance."""

    conn_name: ConnectionName
    client_cert: str
    server_ca_cert: str
    private_key: bytes
    ip_addrs: dict[str, Any]
    database_version: str
    expiration: datetime.datetime
    context: Optional[ssl.SSLContext] = None

    async def create_ssl_context(self, enable_iam_auth: bool = False) -> ssl.SSLContext:
        """Constructs a SSL/TLS context for the given connection info.

        Cache the SSL context to ensure we don't read from disk repeatedly when
        configuring a secure connection.
        """
        # if SSL context is cached, use it
        if self.context is not None:
            return self.context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        # update ssl.PROTOCOL_TLS_CLIENT default
        context.check_hostname = False

        # TODO: remove if/else when Python 3.10 is min version. PEP 644 has been
        # implemented. The ssl module requires OpenSSL 1.1.1 or newer.
        # verify OpenSSL version supports TLSv1.3
        if ssl.HAS_TLSv1_3:
            # force TLSv1.3 if supported by client
            context.minimum_version = ssl.TLSVersion.TLSv1_3
        # fallback to TLSv1.2 for older versions of OpenSSL
        else:
            if enable_iam_auth:
                raise TLSVersionError(
                    f"Your current version of OpenSSL ({ssl.OPENSSL_VERSION}) does not "
                    "support TLSv1.3, which is required to use IAM Authentication.\n"
                    "Upgrade your OpenSSL version to 1.1.1 for TLSv1.3 support."
                )
            logger.warning(
                "TLSv1.3 is not supported with your version of OpenSSL "
                f"({ssl.OPENSSL_VERSION}), falling back to TLSv1.2\n"
                "Upgrade your OpenSSL version to 1.1.1 for TLSv1.3 support."
            )
            context.minimum_version = ssl.TLSVersion.TLSv1_2

        # tmpdir and its contents are automatically deleted after the CA cert
        # and ephemeral cert are loaded into the SSLcontext. The values
        # need to be written to files in order to be loaded by the SSLContext
        async with TemporaryDirectory() as tmpdir:
            ca_filename, cert_filename, key_filename = await write_to_file(
                tmpdir, self.server_ca_cert, self.client_cert, self.private_key
            )
            context.load_cert_chain(cert_filename, keyfile=key_filename)
            context.load_verify_locations(cafile=ca_filename)
        # set class attribute to cache context for subsequent calls
        self.context = context
        return context

    def get_preferred_ip(self, ip_type: IPTypes) -> str:
        """Returns the first IP address for the instance, according to the preference
        supplied by ip_type. If no IP addressess with the given preference are found,
        an error is raised."""
        if ip_type.value in self.ip_addrs:
            return self.ip_addrs[ip_type.value]
        raise CloudSQLIPTypeError(
            "Cloud SQL instance does not have any IP addresses matching "
            f"preference: {ip_type.value}"
        )
