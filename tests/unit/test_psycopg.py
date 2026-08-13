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

import pytest

from google.cloud.sql.connector.psycopg import _proxy
from google.cloud.sql.connector.psycopg import connect

pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"),
    reason="Unix domain sockets (AF_UNIX) not available on this platform",
)


class MockableSocket(socket.socket):
    pass


def mockable_socketpair() -> tuple[MockableSocket, MockableSocket]:
    """Create a socketpair wrapped in MockableSocket to allow method mocking."""
    s1, s2 = socket.socketpair()
    fd1 = s1.detach()
    fd2 = s2.detach()
    ms1 = MockableSocket(socket.AF_UNIX, socket.SOCK_STREAM, fileno=fd1)
    ms2 = MockableSocket(socket.AF_UNIX, socket.SOCK_STREAM, fileno=fd2)
    return ms1, ms2


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


def test_proxy_pending_data() -> None:
    """Test that _proxy forwards pending SSL data correctly."""
    local_client, local_server = socket.socketpair()
    remote_client, remote_server = socket.socketpair()

    class MockSSLSocket:
        def __init__(self, sock: socket.socket) -> None:
            self._sock = sock
            self._pending_calls = [12, 0]  # "pending data" is 12 bytes

        def pending(self) -> int:
            if self._pending_calls:
                return self._pending_calls.pop(0)
            return 0

        def recv(self, bufsize: int, flags: int = 0) -> bytes:
            return self._sock.recv(bufsize, flags)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._sock, name)

    wrapped_remote = MockSSLSocket(remote_client)

    # Pre-populate the socket with data that will be read by forward_pending
    remote_server.sendall(b"pending data")

    # Start proxy in background
    proxy_thread = threading.Thread(
        target=_proxy, args=(local_server, wrapped_remote), daemon=True
    )
    proxy_thread.start()

    # Verify that local_client receives the pending data immediately
    assert local_client.recv(1024) == b"pending data"

    # Clean up
    local_client.close()
    proxy_thread.join(timeout=2.0)

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


@patch("psycopg.connect")
def test_connect_wrapper_failure(mock_psycopg_connect: MagicMock) -> None:
    """Test that connect wrapper cleans up correctly when psycopg.connect fails."""
    mock_remote_sock = MagicMock(spec=ssl.SSLSocket)
    mock_psycopg_connect.side_effect = Exception("connection failed simulated")

    # Call the connect wrapper and expect it to raise
    with pytest.raises(Exception, match="connection failed simulated"):
        connect(
            "127.0.0.1",
            mock_remote_sock,
            user="test_user",
            db="test_db",
            password="test_password",
        )

    # Verify remote socket was closed
    assert mock_remote_sock.close.called

    # Verify cleanup with mocked paths
    with patch("google.cloud.sql.connector.psycopg.tempfile.mkdtemp") as mock_mkdtemp:
        mock_mkdtemp.return_value = "/tmp/mock_temp_dir_failure"

        with (
            patch("google.cloud.sql.connector.psycopg.os.rmdir") as mock_rmdir,
            patch("google.cloud.sql.connector.psycopg.os.remove") as mock_remove,
            patch(
                "google.cloud.sql.connector.psycopg.socket.socket"
            ) as mock_socket_cls,
        ):
            # Mock the local socket to avoid real OS bind/listen
            mock_local_sock = MagicMock()
            mock_socket_cls.return_value = mock_local_sock

            with pytest.raises(Exception, match="connection failed simulated"):
                connect(
                    "127.0.0.1",
                    mock_remote_sock,
                    user="test_user",
                    db="test_db",
                    password="test_password",
                )

            # Verify rmdir and remove were called for cleanup
            mock_rmdir.assert_called_once_with("/tmp/mock_temp_dir_failure")
            mock_remove.assert_called_once()


def test_proxy_remote_eof() -> None:
    """Test that _proxy exits when remote socket receives EOF."""
    local_client, local_server = socket.socketpair()
    remote_client, remote_server = socket.socketpair()

    # Start proxy in background
    proxy_thread = threading.Thread(
        target=_proxy, args=(local_server, remote_client), daemon=True
    )
    proxy_thread.start()

    # Close remote server to trigger EOF on remote_client
    remote_server.close()

    # local_client should receive EOF (b"")
    assert local_client.recv(1024) == b""

    # Wait for proxy thread to finish
    proxy_thread.join(timeout=2.0)
    assert not proxy_thread.is_alive()

    # Sockets should be closed
    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()


def test_proxy_local_recv_error() -> None:
    """Test that _proxy exits when local.recv raises OSError."""
    local_client, local_server = mockable_socketpair()
    remote_client, remote_server = mockable_socketpair()

    # Mock local_server.recv to raise OSError
    local_server.recv = MagicMock(side_effect=OSError("local recv failed"))

    # Trigger selector by sending data to local_server
    local_client.send(b"x")

    # Run proxy. It should detect local is readable, call local.recv() which raises OSError, and exit.
    _proxy(local_server, remote_client)

    # Sockets should be closed
    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()
    remote_server.close()


def test_proxy_remote_send_error() -> None:
    """Test that _proxy exits when remote.sendall raises OSError."""
    local_client, local_server = mockable_socketpair()
    remote_client, remote_server = mockable_socketpair()

    # Mock remote_client.sendall to raise OSError
    remote_client.sendall = MagicMock(side_effect=OSError("remote send failed"))

    # Trigger selector by sending data from local_client -> local_server
    local_client.send(b"x")

    # Run proxy. It reads "x" from local, tries to send to remote, fails, and exits.
    _proxy(local_server, remote_client)

    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()
    remote_server.close()


def test_proxy_remote_recv_error() -> None:
    """Test that _proxy exits when remote.recv raises OSError."""
    local_client, local_server = mockable_socketpair()
    remote_client, remote_server = mockable_socketpair()

    # Mock remote_client.recv to raise OSError
    remote_client.recv = MagicMock(side_effect=OSError("remote recv failed"))

    # Trigger selector by sending data from remote_server -> remote_client
    remote_server.send(b"x")

    # Run proxy. It detects remote is readable, calls remote.recv() which fails, and exits.
    _proxy(local_server, remote_client)

    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()
    remote_server.close()


def test_proxy_local_send_error() -> None:
    """Test that _proxy exits when local.sendall raises OSError."""
    local_client, local_server = mockable_socketpair()
    remote_client, remote_server = mockable_socketpair()

    # Mock local_server.sendall to raise OSError
    local_server.sendall = MagicMock(side_effect=OSError("local send failed"))

    # Trigger selector by sending data from remote_server -> remote_client
    remote_server.send(b"x")

    # Run proxy. It reads "x" from remote, tries to send to local, fails, and exits.
    _proxy(local_server, remote_client)

    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()
    remote_server.close()


def test_proxy_pending_recv_error() -> None:
    """Test that _proxy exits when remote.recv raises OSError during pending check."""
    local_client, local_server = socket.socketpair()
    remote_client, remote_server = mockable_socketpair()

    # Mock remote_client (remote sock in proxy)
    remote_client.pending = MagicMock(return_value=10)
    remote_client.recv = MagicMock(side_effect=OSError("pending recv failed"))

    # Run proxy
    _proxy(local_server, remote_client)

    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()
    remote_server.close()


def test_proxy_pending_local_send_error() -> None:
    """Test that _proxy exits when local.sendall raises OSError during pending check."""
    local_client, local_server = mockable_socketpair()
    remote_client, remote_server = mockable_socketpair()

    # Mock remote_client (remote sock in proxy)
    remote_client.pending = MagicMock(return_value=10)
    remote_client.recv = MagicMock(return_value=b"pending data")

    # Mock local_server.sendall to raise OSError
    local_server.sendall = MagicMock(side_effect=OSError("local send pending failed"))

    # Run proxy
    _proxy(local_server, remote_client)

    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()
    remote_server.close()


@patch.dict("sys.modules", {"psycopg": None})
def test_connect_import_error() -> None:
    """Test that connect raises ImportError if psycopg is not installed."""
    mock_remote_sock = MagicMock(spec=ssl.SSLSocket)

    with pytest.raises(ImportError, match='Unable to import module "psycopg."'):
        connect("127.0.0.1", mock_remote_sock)


def test_connect_cleanup_errors() -> None:
    """Test that connect ignores OSErrors when removing temp files/dirs during cleanup."""
    mock_remote_sock = MagicMock(spec=ssl.SSLSocket)

    def mock_connect_impl(*args: Any, **kwargs: Any) -> MagicMock:
        host = kwargs.get("host")
        socket_path = os.path.join(host, ".s.PGSQL.5432")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(socket_path)
        client.close()
        return MagicMock()

    with (
        patch("psycopg.connect", side_effect=mock_connect_impl),
        patch(
            "google.cloud.sql.connector.psycopg.os.remove",
            side_effect=OSError("remove failed"),
        ) as mock_remove,
        patch(
            "google.cloud.sql.connector.psycopg.os.rmdir",
            side_effect=OSError("rmdir failed"),
        ) as mock_rmdir,
    ):
        conn = connect(
            "127.0.0.1",
            mock_remote_sock,
            user="test_user",
            db="test_db",
            password="test_password",
        )

        assert conn is not None
        assert mock_remove.called
        assert mock_rmdir.called
