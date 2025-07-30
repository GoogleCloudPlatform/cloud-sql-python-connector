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

import platform
import ssl
from typing import Any, TYPE_CHECKING

from google.cloud.sql.connector.exceptions import PlatformNotSupportedError

if TYPE_CHECKING:
    import pytds


def connect(ip_address: str, sock: ssl.SSLSocket, **kwargs: Any) -> "pytds.Connection":
    """Helper function to create a pytds DB-API connection object.

    Args:
        ip_address (str): A string containing an IP address for the Cloud SQL
            instance.
        sock (ssl.SSLSocket): An SSLSocket object created from the Cloud SQL
            server CA cert and ephemeral cert.

    Returns:
        pytds.Connection: A pytds connection to the Cloud SQL
            instance.

    Raises:
        ImportError: The pytds module cannot be imported.
    """
    try:
        import pytds
    except ImportError:
        raise ImportError(
            'Unable to import module "pytds." Please install and try again.'
        )

    db = kwargs.pop("db", None)

    if kwargs.pop("active_directory_auth", False):
        if platform.system() == "Windows":
            # Ignore username and password if using active directory auth
            server_name = kwargs.pop("server_name")
            return pytds.connect(
                database=db,
                auth=pytds.login.SspiAuth(port=1433, server_name=server_name),
                sock=sock,
                **kwargs,
            )
        else:
            raise PlatformNotSupportedError(
                "Active Directory authentication is currently only supported on Windows."
            )

    user = kwargs.pop("user")
    passwd = kwargs.pop("password")
    return pytds.connect(
        ip_address, database=db, user=user, password=passwd, sock=sock, **kwargs
    )
