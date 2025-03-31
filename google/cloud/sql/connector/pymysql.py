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

import ssl
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import pymysql


def connect(
    ip_address: str, sock: ssl.SSLSocket, **kwargs: Any
) -> "pymysql.connections.Connection":
    """Helper function to create a pymysql DB-API connection object.

    Args:
        ip_address (str): A string containing an IP address for the Cloud SQL
            instance.
        sock (ssl.SSLSocket): An SSLSocket object created from the Cloud SQL
            server CA cert and ephemeral cert.

    Returns:
        pymysql.connections.Connection: A pymysql connection to the Cloud SQL
            instance.

    Raises:
        ImportError: The pymysql module cannot be imported.
    """
    try:
        import pymysql
    except ImportError:
        raise ImportError(
            'Unable to import module "pymysql." Please install and try again.'
        )

    # allow automatic IAM database authentication to not require password
    kwargs["password"] = kwargs["password"] if "password" in kwargs else None

    # pop timeout as timeout arg is called 'connect_timeout' for pymysql
    timeout = kwargs.pop("timeout")
    kwargs["connect_timeout"] = kwargs.get("connect_timeout", timeout)
    # Create pymysql connection object and hand in pre-made connection
    conn = pymysql.Connection(host=ip_address, defer_connect=True, **kwargs)
    conn.connect(sock)
    return conn
