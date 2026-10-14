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

import contextlib
import logging
import os
import platform
import selectors
import socket
import ssl
import tempfile
import threading
from types import TracebackType
from typing import Any, Self, TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(name=__name__)

_BUFFER_SIZE = 8192
_DEFAULT_PGSQL_PORT = 5432
_LOOPBACK_HOST = "127.0.0.1"
_UNIX_SOCKET_NAME = ".s.PGSQL.5432"


def _close_socket(sock: socket.socket, *, shutdown: bool = True) -> None:
    """Safely shut down and close a socket, ignoring OSErrors."""
    if shutdown:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    try:
        sock.close()
    except OSError:
        pass


def _forward_bytes(
    src: socket.socket,
    dst: socket.socket,
    src_name: str,
    dst_name: str,
    *,
    nonblocking: bool = False,
) -> bool:
    """Read a chunk of bytes from src and send it to dst.

    Returns:
        bool: True if bytes were forwarded, False on EOF or OSError.
    """
    try:
        if nonblocking:
            src.setblocking(False)
        try:
            data = src.recv(_BUFFER_SIZE)
        finally:
            if nonblocking:
                with contextlib.suppress(OSError):
                    src.setblocking(True)
    except OSError as e:
        if nonblocking and isinstance(e, (ssl.SSLWantReadError, BlockingIOError)):
            return True
        logger.debug(f"Failed to receive from {src_name} socket: {e}")
        return False
    if not data:
        logger.debug(f"EOF reached on {src_name} socket")
        return False
    try:
        dst.sendall(data)
    except OSError as e:
        logger.debug(f"Failed to send to {dst_name} socket: {e}")
        return False
    return True


def _forward_pending(local: socket.socket, remote: "ssl.SSLSocket") -> bool:
    """Read any pending decrypted data from SSL buffer and forward it to local.

    Returns:
        bool: True if EOF was reached or error occurred (should exit).
    """
    if not hasattr(remote, "pending"):
        return False
    pending_bytes = remote.pending()
    if not isinstance(pending_bytes, int):
        return False

    while pending_bytes > 0:
        if not _forward_bytes(remote, local, "remote", "local"):
            return True
        try:
            pending_bytes = remote.pending()
        except OSError:
            break
        if not isinstance(pending_bytes, int):
            break
    return False


def _proxy(local: socket.socket, remote: "ssl.SSLSocket") -> None:
    """Single-threaded selectors-based proxy to avoid SSLSocket thread-safety issues."""
    sel = selectors.DefaultSelector()
    sel.register(local, selectors.EVENT_READ, data="local")
    sel.register(remote, selectors.EVENT_READ, data="remote")

    try:
        while True:
            # First check if there is any pending data in SSL buffer
            if _forward_pending(local, remote):
                break

            events = sel.select()

            for key, _ in events:
                if key.data == "local" and not _forward_bytes(
                    local, remote, "local", "remote"
                ):
                    return
                if key.data == "remote" and not _forward_bytes(
                    remote, local, "remote", "local", nonblocking=True
                ):
                    return
    except OSError as e:
        logger.debug(f"Selector loop error in proxy: {e}")
    finally:
        sel.close()
        _close_socket(local)
        _close_socket(remote)


class _PsycopgProxy:
    """Context manager that sets up a local listener socket and background proxy.

    Encapsulates the platform-specific listener creation (Unix domain socket on
    POSIX, TCP loopback on Windows), background connection acceptance, and
    deterministic cleanup of temporary filesystem resources.
    """

    def __init__(self, ip_address: str, remote_sock: "ssl.SSLSocket") -> None:
        self._ip_address = ip_address
        self._remote_sock = remote_sock
        self._tmpdir: str | None = None
        self._socket_path: str | None = None
        self._local_sock: socket.socket
        self.host: str = ""
        self.port: int = _DEFAULT_PGSQL_PORT

    def __enter__(self) -> Self:
        self._local_sock = self._create_local_socket()
        threading.Thread(target=self._accept_and_proxy, daemon=True).start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            # psycopg never connected (or failed mid-handshake); close the server
            # socket so the proxy thread unblocks and exits cleanly.
            _close_socket(self._local_sock, shutdown=False)
            _close_socket(self._remote_sock, shutdown=False)
        self._cleanup_socket_files()

    def _create_local_socket(self) -> socket.socket:
        """Determine the platform and create a bound local listener socket."""
        if platform.system() == "Windows":
            # On Windows, libpq does not support Unix domain sockets.
            # Use a local TCP loopback socket on an ephemeral port.
            local_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            local_sock.bind((_LOOPBACK_HOST, 0))
            local_sock.listen(1)
            self.host = _LOOPBACK_HOST
            self.port = local_sock.getsockname()[1]
            logger.debug(
                f"['{self._ip_address}']: Created TCP loopback listener "
                f"on {self.host}:{self.port}"
            )
            return local_sock

        self._tmpdir = tempfile.mkdtemp()
        self._socket_path = os.path.join(self._tmpdir, _UNIX_SOCKET_NAME)
        logger.debug(
            f"['{self._ip_address}']: Created Unix socket at {self._socket_path}"
        )
        local_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        local_sock.bind(self._socket_path)
        local_sock.listen(1)
        self.host = self._tmpdir
        self.port = _DEFAULT_PGSQL_PORT
        return local_sock

    def _accept_and_proxy(self) -> None:
        """Accept one connection then proxy bytes until the connection closes."""
        local_conn: socket.socket | None = None
        try:
            local_conn, _ = self._local_sock.accept()
            self._local_sock.close()
            logger.debug(
                f"['{self._ip_address}']: Accepted local connection, starting proxy"
            )
            _proxy(local_conn, self._remote_sock)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"['{self._ip_address}']: Error in accept/proxy thread: {e}")
            if local_conn is not None:
                _close_socket(local_conn)
            _close_socket(self._remote_sock)

    def _cleanup_socket_files(self) -> None:
        """Remove temporary Unix socket file and directory if created."""
        if self._socket_path:
            try:
                os.remove(self._socket_path)
            except OSError:
                pass
        if self._tmpdir:
            try:
                os.rmdir(self._tmpdir)
            except OSError:
                pass


def connect(
    ip_address: str, remote_sock: "ssl.SSLSocket", **kwargs: Any
) -> "psycopg.Connection":
    """Create a psycopg DBAPI connection object.

    Because psycopg does not accept a pre-connected socket, this function
    creates a local listener (Unix domain socket on Unix, TCP loopback on Windows),
    tells psycopg to connect there, and runs a background proxy that forwards bytes
    between that socket and the already-established Cloud SQL TLS connection.

    Args:
        ip_address (str): IP address of the Cloud SQL instance.
        remote_sock (ssl.SSLSocket): SSL/TLS secure socket stream connected to the
            Cloud SQL proxy server.

    Returns:
        psycopg.Connection: A psycopg Connection object for the Cloud SQL instance.
    """
    try:
        import psycopg
    except ImportError:
        raise ImportError(
            'Unable to import module "psycopg." Please install and try again.'
        )

    user = kwargs.pop("user")
    db = kwargs.pop("db")
    passwd = kwargs.pop("password", None)
    # SSL is already handled by the underlying SSLSocket; disable it on the
    # local socket so psycopg does not attempt a second TLS handshake.
    kwargs.pop("sslmode", None)
    timeout = kwargs.pop("timeout", None)
    if timeout is not None:
        kwargs["connect_timeout"] = int(timeout)

    with _PsycopgProxy(ip_address, remote_sock) as proxy:
        logger.debug(
            f"['{ip_address}']: Connecting as user={user} dbname={db} "
            f"to {proxy.host}:{proxy.port}"
        )
        try:
            conn = psycopg.connect(
                user=user,
                dbname=db,
                password=passwd,
                host=proxy.host,
                port=proxy.port,
                sslmode="disable",
                **kwargs,
            )
            logger.debug(f"['{ip_address}']: Connection established")
            return conn
        except Exception as e:
            logger.debug(f"['{ip_address}']: Connection failed: {e}")
            raise
