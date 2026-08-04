# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import socket
import ssl
import threading
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

from google.cloud.sql.connector.psycopg import _proxy
from google.cloud.sql.connector.psycopg import connect


def test_proxy_bidirectional() -> None:
    """Test that _proxy forwards bytes in both directions and exits on EOF."""
    # local_client <-> local_server (simulates psycopg <-> proxy)
    local_client, local_server = socket.socketpair()
    # remote_client <-> remote_server (simulates proxy <-> Cloud SQL)
    remote_client, remote_server = socket.socketpair()

    # Start proxy in a background thread because it blocks
    proxy_thread = threading.Thread(
        target=_proxy, args=(local_server, remote_client), daemon=True
    )
    proxy_thread.start()

    # Test local -> remote
    local_client.sendall(b"hello from local")
    assert remote_server.recv(1024) == b"hello from local"

    # Test remote -> local
    remote_server.sendall(b"hello from remote")
    assert local_client.recv(1024) == b"hello from remote"

    # Close local client (EOF)
    local_client.close()

    # Wait for proxy thread to finish
    proxy_thread.join(timeout=2.0)
    assert not proxy_thread.is_alive()

    # Verify remote socket was also closed by proxy
    try:
        data = remote_server.recv(1024)
        assert data == b""
    except OSError:
        pass  # Closed socket error is also acceptable

    # Clean up remaining sockets
    local_server.close()
    remote_client.close()
    remote_server.close()


@patch("psycopg.connect")
def test_connect_wrapper(mock_psycopg_connect: MagicMock) -> None:
    """Test connect wrapper creates temp socket and calls psycopg.connect with correct arguments."""
    mock_remote_sock = MagicMock(spec=ssl.SSLSocket)

    # We need to mock psycopg.connect to simulate a connection.
    # To prevent the accept thread in connect() from hanging, we make the mock
    # connect to the Unix socket before returning.
    def mock_connect_impl(*args: Any, **kwargs: Any) -> MagicMock:
        host = kwargs.get("host")
        socket_path = os.path.join(host, ".s.PGSQL.5432")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(socket_path)
        client.close()
        return MagicMock()

    mock_psycopg_connect.side_effect = mock_connect_impl

    # Call the connect wrapper
    conn = connect(
        "127.0.0.1",
        mock_remote_sock,
        user="test_user",
        db="test_db",
        password="test_password",
        sslmode="require",
        timeout=30.5,
    )

    assert conn is not None
    assert mock_psycopg_connect.called

    # Verify arguments passed to psycopg.connect
    _, kwargs = mock_psycopg_connect.call_args
    assert kwargs["user"] == "test_user"
    assert kwargs["dbname"] == "test_db"
    assert kwargs["password"] == "test_password"
    assert kwargs["sslmode"] == "disable"
    assert kwargs["connect_timeout"] == 30
    assert "timeout" not in kwargs
    assert "host" in kwargs
    assert kwargs["port"] == 5432

    # Verify temp dir was cleaned up
    assert not os.path.exists(kwargs["host"])
