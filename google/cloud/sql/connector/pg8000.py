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
    import pg8000


def connect(
    ip_address: str, sock: ssl.SSLSocket, **kwargs: Any
) -> "pg8000.dbapi.Connection":
    """Helper function to create a pg8000 DB-API connection object.

    Args:
        ip_address (str): A string containing an IP address for the Cloud SQL
            instance.
        sock (ssl.SSLSocket): An SSLSocket object created from the Cloud SQL
            server CA cert and ephemeral cert.
        kwargs: Additional arguments to pass to the pg8000 connect method.

    Returns:
        pg8000.dbapi.Connection: A pg8000 connection to the Cloud SQL
            instance.

    Raises:
        ImportError: The pg8000 module cannot be imported.
    """
    try:
        import pg8000
    except ImportError:
        raise ImportError(
            'Unable to import module "pg8000." Please install and try again.'
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
