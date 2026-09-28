"""
Copyright 2022 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations


class ConnectorLoopError(Exception):
    """
    Raised when Connector.connect is called with Connector._loop
    in an invalid state (event loop in current thread).
    """



class TLSVersionError(Exception):
    """
    Raised when the required TLS protocol version is not supported.
    """



class CloudSQLIPTypeError(Exception):
    """
    Raised when IP address for the preferred IP type is not found.
    """



class PlatformNotSupportedError(Exception):
    """
    Raised when a feature is not supported on the current platform.
    """



class AutoIAMAuthNotSupported(Exception):
    """
    Exception to be raised when Automatic IAM Authentication is not
    supported with database engine version.
    """



class RefreshNotValidError(Exception):
    """
    Exception to be raised when the task returned from refresh is not valid.
    """



class IncompatibleDriverError(Exception):
    """
    Exception to be raised when the database driver given is for the wrong
    database engine. (i.e. asyncpg for a MySQL database)
    """


class DnsResolutionError(Exception):
    """
    Exception to be raised when an instance connection name can not be resolved
    from a DNS record.
    """


class DnsLoopError(DnsResolutionError):
    """
    Exception to be raised when a CNAME loop is detected during DNS resolution.
    """


class CacheClosedError(Exception):
    """
    Exception to be raised when a ConnectionInfoCache can not be accessed after
    it is closed.
    """


class ClosedConnectorError(Exception):
    """
    Exception to be raised when a Connector is closed and connect method is
    called on it.
    """


class CloudSQLConnectionError(Exception):
    """
    Exception to be raised when a connection cannot be established to a Cloud SQL instance.
    """


class ResourceExhaustedError(CloudSQLConnectionError):
    """
    Exception to be raised when a connection cannot be established because
    the SQL Data Service is busy / in cooldown due to resource exhaustion.
    """

    def __init__(
        self,
        message: str,
        connection_name: str | None = None,
        raw_error: Exception | None = None,
    ) -> None:
        self.message = message
        self.connection_name = connection_name
        self.raw_error = raw_error
        super().__init__(
            f"[{connection_name}] {message}: {raw_error}"
            if connection_name and raw_error
            else f"[{connection_name}] {message}"
            if connection_name
            else message
        )

