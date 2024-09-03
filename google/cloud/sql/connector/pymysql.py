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

import socket
import ssl
from typing import Any, TYPE_CHECKING

SERVER_PROXY_PORT = 3307

if TYPE_CHECKING:
    import pymysql


def connect(
    ip_address: str, ctx: ssl.SSLContext, server_name: str, **kwargs: Any
) -> "pymysql.Connection":
    """Helper function to create a pymysql DB-API connection object.

    Args:
        ip_address (str): The IP address for the Cloud SQL instance.

        ctx (ssl.SSLContext): An SSL/TLS object created from the Cloud SQL
            server CA cert and ephemeral cert.

        server_name (str): The server name of the Cloud SQL instance. Used to
            verify the server identity for CAS instances.

    Returns:
        (pymysql.Connection) A pymysql connection object to the Cloud SQL
            instance.
    """
    try:
        import pymysql
    except ImportError:
        raise ImportError(
            'Unable to import module "pymysql." Please install and try again.'
        )

    # allow automatic IAM database authentication to not require password
    kwargs["password"] = kwargs["password"] if "password" in kwargs else None
    # if CAS instance, check server name
    if ctx.check_hostname:
        server_name = server_name
    else:
        server_name = None
    # Create socket and wrap with context.
    sock = ctx.wrap_socket(
        socket.create_connection((ip_address, SERVER_PROXY_PORT)),
        server_hostname=server_name,
    )
    # pop timeout as timeout arg is called 'connect_timeout' for pymysql
    timeout = kwargs.pop("timeout")
    kwargs["connect_timeout"] = kwargs.get("connect_timeout", timeout)
    # Create pymysql connection object and hand in pre-made connection
    conn = pymysql.Connection(host=ip_address, defer_connect=True, **kwargs)
    conn.connect(sock)
    return conn
