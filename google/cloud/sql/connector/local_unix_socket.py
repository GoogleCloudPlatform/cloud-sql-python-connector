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

def connect(
    host: str, sock: ssl.SSLSocket, **kwargs: Any
) -> "ssl.SSLSocket":
    """Helper function to retrieve the socket for local UNIX sockets.

    Args:
        host (str): A string containing the socket path used by the local proxy.
        sock (ssl.SSLSocket): An SSLSocket object created from the Cloud SQL
            server CA cert and ephemeral cert.
        kwargs: Additional arguments to pass to the local UNIX socket connect method.

    Returns:
        ssl.SSLSocket: The same socket
    """
    
    return sock
