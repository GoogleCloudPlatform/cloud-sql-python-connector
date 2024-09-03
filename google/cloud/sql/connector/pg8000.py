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
    import pg8000


def connect(
    ip_address: str, ctx: ssl.SSLContext, server_name: str, **kwargs: Any
) -> "pg8000.dbapi.Connection":
    """Helper function to create a pg8000 DB-API connection object.

    Args:
        ip_address (str): The IP address for the Cloud SQL instance.

        ctx (ssl.SSLContext): An SSL/TLS object created from the Cloud SQL
            server CA cert and ephemeral cert.

        server_name (str): The server name of the Cloud SQL instance. Used to
            verify the server identity for CAS instances.

    Returns:
        (pg8000.dbapi.Connection) A pg8000 connection object to the Cloud SQL
            instance.
    """
    try:
        import pg8000
    except ImportError:
        raise ImportError(
            'Unable to import module "pg8000." Please install and try again.'
        )
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

    user = kwargs.pop("user")
    db = kwargs.pop("db")
    passwd = kwargs.pop("password", None)
    return pg8000.dbapi.connect(
        user,
        database=db,
        password=passwd,
        sock=sock,
        **kwargs,
    )
