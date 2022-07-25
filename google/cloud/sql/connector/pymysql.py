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
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
) -> "pymysql.connections.Connection":
    """Helper function to create a pymysql DB-API connection object.

    :type ip_address: str
    :param ip_address: A string containing an IP address for the Cloud SQL
        instance.

    :type ctx: ssl.SSLContext
    :param ctx: An SSLContext object created from the Cloud SQL server CA
        cert and ephemeral cert.

    :rtype: pymysql.Connection
    :returns: A PyMySQL Connection object for the Cloud SQL instance.
    """
    try:
        import pymysql
    except ImportError:
        raise ImportError(
            'Unable to import module "pymysql." Please install and try again.'
        )

    # Create socket and wrap with context.
    sock = ctx.wrap_socket(
        socket.create_connection((ip_address, SERVER_PROXY_PORT)),
        server_hostname=ip_address,
    )

    # Create pymysql connection object and hand in pre-made connection
    conn = pymysql.Connection(host=ip_address, defer_connect=True, **kwargs)
    conn.connect(sock)
    return conn
