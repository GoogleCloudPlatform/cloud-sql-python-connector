"""
Copyright 2026 Google LLC

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

from __future__ import annotations

from collections.abc import Callable
import socket
import ssl
from typing import Any

MAX_PG_STARTUP_PACKET_LEN = 10000
PG_PROTOCOL_VERSION_30 = 196608  # 0x00030000
PG_SSL_REQUEST_CODE = 80877103  # 0x04d2162f
PG_GSS_ENC_REQUEST_CODE = 80877104  # 0x04d21630


class PostgresConnection:
    """Wraps a socket to inspect initial client-side PostgreSQL v3 StartupMessage bytes.

    Extracts the (user, database) principal pair for Auto-IAM refresh probes.
    Handles chunked streaming across multiple write/send operations.
    Once the startup message is detected or determined not to be a PostgreSQL v3
    startup packet, startup_message_sent is set to True, the internal buffer is
    cleared, and all subsequent writes pass through directly with zero overhead.

    Like standard Python socket and stream wrappers, callers own synchronization
    for concurrent writes; no internal lock is acquired on the write path.
    """

    def __init__(
        self,
        sock: socket.socket | ssl.SSLSocket,
        on_startup: Callable[[str, str], None],
    ) -> None:
        self._sock = sock
        self._on_startup = on_startup
        self._buf = bytearray()
        self.startup_message_sent = False

    def _inspect(self, data: bytes | bytearray | memoryview) -> None:
        if self.startup_message_sent or not data:
            return
        self._buf.extend(data)
        user, database, complete = parse_postgres_startup_packet(self._buf)
        if complete:
            self.startup_message_sent = True
            self._buf.clear()
            if user:
                self._on_startup(user, database)
        elif len(self._buf) > MAX_PG_STARTUP_PACKET_LEN + 16:
            self.startup_message_sent = True
            self._buf.clear()

    def send(
        self,
        data: bytes | bytearray | memoryview,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        sent = self._sock.send(data, *args, **kwargs)
        if not self.startup_message_sent:
            chunk = data[:sent] if isinstance(sent, int) else data
            if chunk:
                self._inspect(chunk)
        return sent

    def sendall(
        self,
        data: bytes | bytearray | memoryview,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._sock.sendall(data, *args, **kwargs)
        if not self.startup_message_sent and data:
            self._inspect(data)

    def write(self, data: bytes | bytearray | memoryview) -> int:
        written = (
            self._sock.write(data)
            if hasattr(self._sock, "write")
            else self._sock.send(data)
        )
        if not self.startup_message_sent:
            chunk = data[:written] if isinstance(written, int) else data
            if chunk:
                self._inspect(chunk)
        return written

    @property
    def _io_refs(self) -> int:
        return getattr(self._sock, "_io_refs", 0)

    @_io_refs.setter
    def _io_refs(self, value: int) -> None:
        self._sock._io_refs = value  # type: ignore[union-attr]

    def makefile(
        self,
        mode: str = "r",
        buffering: int | None = None,
        *,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> Any:
        """Returns an I/O stream connected to this wrapped socket so makefile writes are inspected."""
        return socket.socket.makefile(  # type: ignore[call-overload]
            self,
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    def close(self) -> None:
        self._sock.close()

    def fileno(self) -> int:
        return self._sock.fileno()

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *args: object) -> Any:
        if hasattr(self._sock, "__exit__"):
            return self._sock.__exit__(*args)
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sock, name)


def parse_postgres_startup_packet(
    buf: bytes | bytearray | memoryview,
) -> tuple[str, str, bool]:
    """Parses a buffer to extract the PostgreSQL v3 StartupMessage (user, database) pair.

    Returns:
        (user, database, complete):
            complete is True if the packet was fully parsed (or rejected),
            False if more bytes are needed (partial packet).
    """
    data = bytes(buf)
    # Step 1: Skip prepended SSLRequest (80877103) or GSSENCRequest (80877104) (can occur in succession).
    while len(data) >= 8:
        pkt_len = int.from_bytes(data[0:4], byteorder="big")
        code = int.from_bytes(data[4:8], byteorder="big")
        if pkt_len == 8 and (
            code == PG_SSL_REQUEST_CODE or code == PG_GSS_ENC_REQUEST_CODE
        ):
            data = data[8:]
        else:
            break

    # Step 2: Wait for at least 8 bytes (4-byte packet length + 4-byte protocol code).
    if len(data) < 8:
        return "", "", False

    pkt_len = int.from_bytes(data[0:4], byteorder="big")
    code = int.from_bytes(data[4:8], byteorder="big")

    # Step 3: Validate protocol version (v3.0) and packet length bounds.
    if (
        code != PG_PROTOCOL_VERSION_30
        or pkt_len < 8
        or pkt_len > MAX_PG_STARTUP_PACKET_LEN
    ):
        return "", "", True

    # Step 4: Wait until the complete packet body has arrived.
    if len(data) < pkt_len:
        return "", "", False

    # Step 5: Decode null-terminated key-value pairs (user, database) from the payload.
    payload = data[8:pkt_len]
    user = ""
    database = ""
    while payload and payload[0] != 0:
        try:
            k_end = payload.index(0)
        except ValueError:
            break
        key = payload[:k_end].decode("utf-8", errors="replace")
        payload = payload[k_end + 1 :]
        try:
            v_end = payload.index(0)
        except ValueError:
            break
        val = payload[:v_end].decode("utf-8", errors="replace")
        payload = payload[v_end + 1 :]

        if key == "user":
            user = val
        elif key == "database":
            database = val

    if user and not database:
        database = user

    # Step 6: Successfully extracted credentials.
    return user, database, True


def build_postgres_startup_packet(user: str, database: str) -> bytes:
    """Builds a PostgreSQL v3.0 StartupMessage for (user, database)."""
    if not database:
        database = user
    body = (
        b"user\x00"
        + user.encode("utf-8")
        + b"\x00database\x00"
        + database.encode("utf-8")
        + b"\x00\x00"
    )
    total_len = 8 + len(body)
    return total_len.to_bytes(4, byteorder="big") + b"\x00\x03\x00\x00" + body


def build_terminate_packet() -> bytes:
    """Builds a PostgreSQL Terminate packet ('X' followed by int32 length 4)."""
    return b"X\x00\x00\x00\x04"
