"""
Copyright 2025 Google LLC

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
import threading

SERVER_PROXY_PORT = 3307

if TYPE_CHECKING:
    import psycopg


def connect(
    host: str, sock: ssl.SSLSocket, **kwargs: Any
) -> "psycopg.Connection":
    """Helper function to create a psycopg DB-API connection object.

    Args:
        host (str): A string containing the socket path used by the local proxy.
        sock (ssl.SSLSocket): An SSLSocket object created from the Cloud SQL
            server CA cert and ephemeral cert.
        kwargs: Additional arguments to pass to the psycopg connect method.

    Returns:
        psycopg.Connection: A psycopg connection to the Cloud SQL
            instance.

    Raises:
        ImportError: The psycopg module cannot be imported.
    """
    try:
        from psycopg import Connection
    except ImportError:
        raise ImportError(
            'Unable to import module "psycopg." Please install and try again.'
        )

    user = kwargs.pop("user")
    db = kwargs.pop("db")
    passwd = kwargs.pop("password", None)

    kwargs.pop("timeout", None)

    conn = Connection.connect(
        f"host={host} port={SERVER_PROXY_PORT} dbname={db} user={user} password={passwd} sslmode=require",
        **kwargs
    )

    return conn
