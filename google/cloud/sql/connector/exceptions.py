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


class ConnectorLoopError(Exception):
    """
    Raised when Connector.connect is called with Connector._loop
    in an invalid state (event loop in current thread).
    """

    pass


class TLSVersionError(Exception):
    """
    Raised when the required TLS protocol version is not supported.
    """

    pass


class CloudSQLIPTypeError(Exception):
    """
    Raised when IP address for the preferred IP type is not found.
    """

    pass


class PlatformNotSupportedError(Exception):
    """
    Raised when a feature is not supported on the current platform.
    """

    pass


class CredentialsTypeError(Exception):
    """
    Raised when credentials parameter is not proper type.
    """

    pass


class AutoIAMAuthNotSupported(Exception):
    """
    Exception to be raised when Automatic IAM Authentication is not
    supported with database engine version.
    """

    pass
