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


def test_proxy_happy_path_sequential() -> None:
    """Test that _proxy forwards sequential request/response traffic cleanly without errors."""
    local_client, local_proxy = socket.socketpair(
        socket.AF_UNIX, socket.SOCK_STREAM
    )
    remote_proxy, remote_server = socket.socketpair(
        socket.AF_UNIX, socket.SOCK_STREAM
    )

    t = threading.Thread(
        target=_proxy, args=(local_proxy, remote_proxy), daemon=True
    )
    t.start()

    # Step 1: Client sends query
    local_client.sendall(b"SELECT 1;")
    received_query = remote_server.recv(1024)
    assert received_query == b"SELECT 1;"

    # Step 2: Server sends response
    remote_server.sendall(b"RESULT 1")
    received_resp = local_client.recv(1024)
    assert received_resp == b"RESULT 1"

    # Step 3: Client closes connection cleanly
    local_client.shutdown(socket.SHUT_RDWR)
    local_client.close()
    remote_server.close()
    t.join(timeout=2.0)
    assert not t.is_alive()


def test_proxy_backpressure_and_clean_teardown() -> None:
    """Demonstrate that Cloud SQL's single-threaded selector proxy exits cleanly

    without deadlocking on teardown.
    """
    local_client, local_proxy = socket.socketpair(
        socket.AF_UNIX, socket.SOCK_STREAM
    )
    remote_proxy, remote_server = socket.socketpair(
        socket.AF_UNIX, socket.SOCK_STREAM
    )

    t_proxy = threading.Thread(
        target=_proxy, args=(local_proxy, remote_proxy), daemon=True
    )
    t_proxy.start()

    # Step 1: Client sends query
    local_client.sendall(b"SELECT 1;")
    assert remote_server.recv(1024) == b"SELECT 1;"

    # Step 2: Server sends response
    remote_server.sendall(b"RESULT 1")
    assert local_client.recv(1024) == b"RESULT 1"

    # Step 3: Client closes connection while server is open
    local_client.close()

    # Single-threaded proxy terminates immediately without deadlocking
    t_proxy.join(timeout=2.0)
    assert (
        not t_proxy.is_alive()
    ), "Cloud SQL proxy must terminate cleanly without deadlocks"

    remote_server.close()


def test_proxy_pending_oserror_in_loop() -> None:
    """Test that _proxy pending loop handles OSError on pending() and continues."""
    local_client, local_proxy = mockable_socketpair()
    remote_proxy, remote_server = mockable_socketpair()

    # Add pending mock to real socket. First call returns 10, second raises OSError.
    remote_proxy.pending = MagicMock(side_effect=[10, OSError("pending failed")])

    # Send data to be read by recv in pending loop
    remote_server.sendall(b"pending data")

    # Start proxy in thread because it will block on select() after pending fails
    t = threading.Thread(target=_proxy, args=(local_proxy, remote_proxy), daemon=True)
    t.start()

    # Verify local_client received the pending data
    assert local_client.recv(1024) == b"pending data"

    # Now trigger proxy exit by closing local_client
    local_client.close()

    t.join(timeout=2.0)
    assert not t.is_alive()

    remote_server.close()


def test_proxy_pending_non_int() -> None:
    """Test that _proxy pending check handles non-int return values from pending()."""
    local_client, local_proxy = mockable_socketpair()
    remote_proxy, remote_server = mockable_socketpair()

    # First call returns non-int. Should return False (goes to select)
    remote_proxy.pending = MagicMock(return_value="not an int")

    # We need to run it in a thread because it will block on select
    t = threading.Thread(target=_proxy, args=(local_proxy, remote_proxy), daemon=True)
    t.start()

    # Trigger exit.
    local_client.close()
    t.join(timeout=2.0)
    assert not t.is_alive()
    remote_server.close()


def test_proxy_pending_non_int_in_loop() -> None:
    """Test that _proxy pending loop handles non-int return values from pending() in loop."""
    local_client, local_proxy = mockable_socketpair()
    remote_proxy, remote_server = mockable_socketpair()

    # Second call returns non-int.
    remote_proxy.pending = MagicMock(side_effect=[10, "not an int"])
    remote_server.sendall(b"data")

    t = threading.Thread(target=_proxy, args=(local_proxy, remote_proxy), daemon=True)
    t.start()

    assert local_client.recv(1024) == b"data"

    local_client.close()
    t.join(timeout=2.0)
    assert not t.is_alive()
    remote_server.close()


def test_proxy_pending_recv_eof() -> None:
    """Test that _proxy pending loop handles remote recv EOF."""
    local_client, local_server = mockable_socketpair()
    remote_client, remote_server = mockable_socketpair()

    remote_client.pending = MagicMock(return_value=10)
    # Mock recv to return EOF
    remote_client.recv = MagicMock(return_value=b"")

    # Run proxy. It should call forward_pending, which calls recv, gets EOF,
    # and returns True. This breaks the loop and proxy exits.
    _proxy(local_server, remote_client)

    # Sockets should be closed
    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()
    remote_server.close()


def test_proxy_select_oserror() -> None:
    """Test that _proxy loop handles OSError in select()."""
    local_client, local_server = mockable_socketpair()
    remote_client, remote_server = mockable_socketpair()

    with patch(
        "google.cloud.sql.connector.psycopg.selectors.DefaultSelector"
    ) as mock_sel_cls:
        mock_sel = MagicMock()
        mock_sel.select.side_effect = OSError("select failed")
        mock_sel_cls.return_value = mock_sel

        # Run proxy. It should catch OSError on select() and exit loop to finally block.
        _proxy(local_server, remote_client)

    assert local_server.fileno() == -1
    assert remote_client.fileno() == -1

    local_client.close()
    remote_server.close()


def test_proxy_finally_cleanup_errors() -> None:
    """Test that _proxy finally block ignores OSErrors during socket shutdown/close."""
    local_client, local_server = mockable_socketpair()
    remote_client, remote_server = mockable_socketpair()

    real_local_shutdown = local_server.shutdown
    def mock_local_shutdown(how):
        try:
            real_local_shutdown(how)
        except OSError:
            pass
        raise OSError("shutdown failed")
    local_server.shutdown = MagicMock(side_effect=mock_local_shutdown)

    real_local_close = local_server.close
    def mock_local_close():
        real_local_close()
        raise OSError("close failed")
    local_server.close = MagicMock(side_effect=mock_local_close)

    real_remote_shutdown = remote_client.shutdown
    def mock_remote_shutdown(how):
        try:
            real_remote_shutdown(how)
        except OSError:
            pass
        raise OSError("shutdown failed")
    remote_client.shutdown = MagicMock(side_effect=mock_remote_shutdown)

    real_remote_close = remote_client.close
    def mock_remote_close():
        real_remote_close()
        raise OSError("close failed")
    remote_client.close = MagicMock(side_effect=mock_remote_close)

    # Trigger exit by closing client
    local_client.close()

    # Run proxy. It should handle the exceptions in finally block.
    _proxy(local_server, remote_client)

    remote_server.close()


@patch("google.cloud.sql.connector.psycopg._proxy")
def test_accept_and_proxy_cleanup_errors(mock_proxy_fn: MagicMock) -> None:
    """Test that accept_and_proxy thread handles errors during cleanup on exception."""
    # Make _proxy raise an exception to trigger the except block in _accept_and_proxy
    mock_proxy_fn.side_effect = Exception("proxy crash")

    mock_unix_conn = MagicMock(spec=socket.socket)
    mock_unix_conn.shutdown.side_effect = OSError("unix conn shutdown failed")
    mock_unix_conn.close.side_effect = OSError("unix conn close failed")

    mock_remote_sock = MagicMock(spec=ssl.SSLSocket)
    mock_remote_sock.shutdown.side_effect = OSError("remote shutdown failed")

    # Mock socket.socket to return a mock local_sock that returns our mock_unix_conn
    real_socket = socket.socket
    mock_local_sock = MagicMock()
    mock_local_sock.accept.return_value = (mock_unix_conn, ("path",))

    def socket_side_effect(family, type, proto=0, fileno=None):
        if family == socket.AF_UNIX:
            return mock_local_sock
        return real_socket(family, type, proto, fileno)

    event = threading.Event()
    def remote_close_fn():
        event.set()
        raise OSError("remote close failed")
    mock_remote_sock.close.side_effect = remote_close_fn

    with patch("socket.socket", side_effect=socket_side_effect), patch(
        "psycopg.connect"
    ) as mock_psycopg_connect:
        mock_psycopg_connect.return_value = MagicMock()

        connect(
            "127.0.0.1",
            mock_remote_sock,
            user="test_user",
            db="test_db",
            password="test_password",
        )

        # Wait for the accept_and_proxy thread to finish cleanup
        assert event.wait(timeout=2.0)

        # Verify mock_unix_conn shutdown and close were called
        mock_unix_conn.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        mock_unix_conn.close.assert_called_once()
        mock_remote_sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        mock_remote_sock.close.assert_called_once()


@patch("psycopg.connect")
def test_connect_wrapper_failure_cleanup_errors(mock_psycopg_connect: MagicMock) -> None:
    """Test that connect wrapper ignores OSErrors during cleanup on connection failure."""
    mock_remote_sock = MagicMock(spec=ssl.SSLSocket)
    mock_remote_sock.close.side_effect = OSError("remote close failed")

    mock_psycopg_connect.side_effect = Exception("connection failed simulated")

    mock_local_sock = MagicMock()
    mock_local_sock.close.side_effect = OSError("local close failed")

    real_socket = socket.socket
    def socket_side_effect(family, type, proto=0, fileno=None):
        if family == socket.AF_UNIX:
            return mock_local_sock
        return real_socket(family, type, proto, fileno)

    with (
        patch("socket.socket", side_effect=socket_side_effect),
        pytest.raises(Exception, match="connection failed simulated"),
    ):
        connect(
            "127.0.0.1",
            mock_remote_sock,
            user="test_user",
            db="test_db",
            password="test_password",
        )

    mock_local_sock.close.assert_called_once()
    assert mock_remote_sock.close.call_count >= 1


