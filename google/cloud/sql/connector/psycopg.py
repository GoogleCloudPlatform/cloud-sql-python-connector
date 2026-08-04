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
import socket
import ssl
import tempfile
import threading
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(name=__name__)

_CHUNK_SIZE = 8 * 1024  # bytes per recv() call inside the proxy forwarding loop


def _proxy(local: socket.socket, remote: "ssl.SSLSocket") -> None:
    """Bidirectionally proxy bytes between a local Unix socket and a remote
    SSL socket.

    Spawns one daemon thread for the remote→local direction and runs the
    local→remote direction in the calling thread. Blocks until the calling
    thread's direction reaches EOF or a socket error, at which point both
    sockets are closed so the other thread also unblocks and exits.

    Args:
        local: The Unix domain socket connected to the database driver.
        remote: The SSL socket connected to the Cloud SQL proxy server.
    """
    def forward(src: Any, dst: Any) -> None:
        buf = bytearray(_CHUNK_SIZE)
        view = memoryview(buf)
        try:
            while True:
                n = src.recv_into(view)
                if n == 0:
                    logger.debug("psycopg proxy: EOF on %s, closing both sockets", src)
                    break
                dst.sendall(view[:n])
        except (OSError, ssl.SSLError) as e:
            logger.debug("psycopg proxy: socket error on %s: %s", src, e)
        finally:
            # Close both ends so the sibling thread also unblocks.
            for s in (local, remote):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass

    threading.Thread(target=forward, args=(remote, local), daemon=True).start()
    forward(local, remote)  # run in calling thread rather than spawning a third


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

    tmpdir = tempfile.mkdtemp()
    socket_path = os.path.join(tmpdir, ".s.PGSQL.5432")
    logger.debug("psycopg: created Unix socket at %s", socket_path)

    local_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    local_sock.bind(socket_path)
    local_sock.listen(1)

    def _accept_and_proxy() -> None:
        """Accept one connection then proxy bytes until the connection closes."""
        try:
            unix_conn, _ = local_sock.accept()
            local_sock.close()
            logger.debug("psycopg proxy: accepted connection, starting proxy")
        except OSError as e:
            logger.debug("psycopg proxy: accept failed: %s", e)
            try:
                remote_sock.close()
            except OSError:
                pass
            return
        _proxy(unix_conn, remote_sock)

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
