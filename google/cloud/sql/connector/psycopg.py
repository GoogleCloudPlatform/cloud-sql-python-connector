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

import logging
import os
import selectors
import socket
import ssl
import tempfile
import threading
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(name=__name__)


def _proxy(local: socket.socket, remote: "ssl.SSLSocket") -> None:
    """Single-threaded selectors-based proxy to avoid SSLSocket thread-safety issues."""
    sel = selectors.DefaultSelector()
    sel.register(local, selectors.EVENT_READ, data="local")
    sel.register(remote, selectors.EVENT_READ, data="remote")

    def forward_pending() -> bool:
        """Read any pending decrypted data from SSL buffer and forward it.
        Returns True if EOF was reached or error occurred (should exit).
        """
        if not hasattr(remote, "pending"):
            return False
        pending_bytes = remote.pending()
        if not isinstance(pending_bytes, int):
            return False

        while pending_bytes > 0:
            try:
                data = remote.recv(8192)
            except OSError as e:
                logger.debug("psycopg proxy: remote recv pending error: %s", e)
                return True
            if not data:
                logger.debug("psycopg proxy: remote pending EOF")
                return True
            try:
                local.sendall(data)
            except OSError as e:
                logger.debug("psycopg proxy: local send pending error: %s", e)
                return True
            try:
                pending_bytes = remote.pending()
            except OSError:
                break
            if not isinstance(pending_bytes, int):
                break
        return False

    try:
        while True:
            # First check if there is any pending data in SSL buffer
            if forward_pending():
                break

            events = sel.select()

            for key, mask in events:
                if key.data == "local":
                    try:
                        data = local.recv(8192)
                    except OSError as e:
                        logger.debug("psycopg proxy: local recv error: %s", e)
                        return
                    if not data:
                        logger.debug("psycopg proxy: local EOF")
                        return
                    try:
                        remote.sendall(data)
                    except OSError as e:
                        logger.debug("psycopg proxy: remote send error: %s", e)
                        return
                elif key.data == "remote":
                    try:
                        data = remote.recv(8192)
                    except OSError as e:
                        logger.debug("psycopg proxy: remote recv error: %s", e)
                        return
                    if not data:
                        logger.debug("psycopg proxy: remote EOF")
                        return
                    try:
                        local.sendall(data)
                    except OSError as e:
                        logger.debug("psycopg proxy: local send error: %s", e)
                        return
    except OSError as e:
        logger.debug("psycopg proxy: OSError in loop: %s", e)
    finally:
        sel.close()
        for s in (local, remote):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


def connect(
    ip_address: str, remote_sock: "ssl.SSLSocket", **kwargs: Any
) -> "psycopg.Connection":
    """Create a psycopg DBAPI connection object.

    Because psycopg does not accept a pre-connected socket, this function
    creates a temporary Unix domain socket, tells psycopg to connect there,
    and runs a background proxy that forwards bytes between that socket and
    the already-established Cloud SQL TLS connection.

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

    if not hasattr(socket, "AF_UNIX"):
        raise NotImplementedError(
            "Unix domain sockets (AF_UNIX) are not supported on this platform"
        )

    tmpdir = tempfile.mkdtemp()
    socket_path = os.path.join(tmpdir, ".s.PGSQL.5432")
    logger.debug("psycopg: created Unix socket at %s", socket_path)

    local_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    local_sock.bind(socket_path)
    local_sock.listen(1)

    def _accept_and_proxy() -> None:
        """Accept one connection then proxy bytes until the connection closes."""
        unix_conn = None
        try:
            unix_conn, _ = local_sock.accept()
            local_sock.close()
            logger.debug("psycopg proxy: accepted connection, starting proxy")
            _proxy(unix_conn, remote_sock)
        except Exception as e:  # noqa: BLE001
            logger.debug("psycopg proxy: error in accept/proxy thread: %s", e)
            # Ensure cleanup on any exception
            if unix_conn:
                try:
                    unix_conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    unix_conn.close()
                except OSError:
                    pass
            try:
                remote_sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                remote_sock.close()
            except OSError:
                pass

    threading.Thread(target=_accept_and_proxy, daemon=True).start()

    user = kwargs.pop("user")
    db = kwargs.pop("db")
    passwd = kwargs.pop("password", None)
    # SSL is already handled by the underlying SSLSocket; disable it on the
    # Unix socket so psycopg does not attempt a second TLS handshake.
    kwargs.pop("sslmode", None)
    timeout = kwargs.pop("timeout", None)
    if timeout is not None:
        kwargs["connect_timeout"] = int(timeout)

    logger.debug("psycopg: connecting as user=%s dbname=%s", user, db)
    try:
        conn = psycopg.connect(
            user=user,
            dbname=db,
            password=passwd,
            host=tmpdir,
            port=5432,
            sslmode="disable",
            **kwargs,
        )
        logger.debug("psycopg: connection established")
        return conn
    except Exception as e:
        logger.debug("psycopg: connection failed: %s", e)
        # psycopg never connected (or failed mid-handshake); close the server
        # socket so the proxy thread unblocks and exits cleanly.
        try:
            local_sock.close()
        except OSError:
            pass
        try:
            remote_sock.close()
        except OSError:
            pass
        raise
    finally:
        # The socket file and its parent directory are only needed during the
        # initial connect() call; remove them now regardless of outcome.
        try:
            os.remove(socket_path)
        except OSError:
            pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
