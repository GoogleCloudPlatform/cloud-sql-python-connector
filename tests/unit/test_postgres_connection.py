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

import socket
from unittest.mock import MagicMock

from google.cloud.sql.connector.postgres_connection import build_postgres_startup_packet
from google.cloud.sql.connector.postgres_connection import build_terminate_packet
from google.cloud.sql.connector.postgres_connection import MAX_PG_STARTUP_PACKET_LEN
from google.cloud.sql.connector.postgres_connection import parse_postgres_startup_packet
from google.cloud.sql.connector.postgres_connection import PostgresConnection


def test_parse_postgres_startup_packet_empty_or_short() -> None:
    """Test packet parser with incomplete data."""
    user, db, complete = parse_postgres_startup_packet(b"")
    assert not complete
    assert user == ""
    assert db == ""

    user, db, complete = parse_postgres_startup_packet(b"\x00\x00\x00\x10")
    assert not complete
    assert user == ""
    assert db == ""


def test_parse_postgres_startup_packet_complete() -> None:
    """Test packet parser with full StartupMessage."""
    pkt = build_postgres_startup_packet("test-user@example.com", "test-db")
    user, db, complete = parse_postgres_startup_packet(pkt)
    assert complete
    assert user == "test-user@example.com"
    assert db == "test-db"


def test_parse_postgres_startup_packet_prepended_ssl_request() -> None:
    """Test packet parser handles prepended SSLRequest."""
    ssl_req = b"\x00\x00\x00\x08\x04\xd2\x16\x2f"
    startup = build_postgres_startup_packet("ssl-user@example.com", "ssl-db")
    user, db, complete = parse_postgres_startup_packet(ssl_req + startup)
    assert complete
    assert user == "ssl-user@example.com"
    assert db == "ssl-db"


def test_build_terminate_packet() -> None:
    """Test PostgreSQL Terminate packet."""
    assert build_terminate_packet() == b"X\x00\x00\x00\x04"


def test_postgres_connection_single_write() -> None:
    """Test PostgresConnection handles full StartupMessage in a single write."""
    mock_sock = MagicMock()
    mock_sock.sendall = MagicMock()
    captured: list[tuple[str, str]] = []

    conn = PostgresConnection(
        mock_sock,
        on_startup=lambda u, d: captured.append((u, d)),
    )

    pkt = build_postgres_startup_packet("alice@example.com", "alicedb")
    conn.sendall(pkt)

    assert captured == [("alice@example.com", "alicedb")]
    assert conn.startup_message_sent
    mock_sock.sendall.assert_called_once_with(pkt)

    # Subsequent writes pass through with zero overhead
    conn.sendall(b"QSELECT 1;\x00")
    assert len(captured) == 1
    assert mock_sock.sendall.call_count == 2


def test_postgres_connection_chunked_writes() -> None:
    """Test PostgresConnection buffers chunked writes (1 byte then rest)."""
    mock_sock = MagicMock()
    mock_sock.sendall = MagicMock()
    captured: list[tuple[str, str]] = []

    conn = PostgresConnection(
        mock_sock,
        on_startup=lambda u, d: captured.append((u, d)),
    )

    pkt = build_postgres_startup_packet("bob@example.com", "bobdb")

    # First write: single 1-byte chunk
    conn.sendall(pkt[:1])
    assert not captured
    assert not conn.startup_message_sent
    mock_sock.sendall.assert_called_once_with(pkt[:1])

    # Second write: remainder
    conn.sendall(pkt[1:])
    assert captured == [("bob@example.com", "bobdb")]
    assert conn.startup_message_sent
    assert mock_sock.sendall.call_count == 2


def test_postgres_connection_byte_by_byte_streaming() -> None:
    """Test PostgresConnection handles fine-grained byte-by-byte streaming."""
    mock_sock = MagicMock()
    mock_sock.send = MagicMock(return_value=1)
    captured: list[tuple[str, str]] = []

    conn = PostgresConnection(
        mock_sock,
        on_startup=lambda u, d: captured.append((u, d)),
    )

    pkt = build_postgres_startup_packet("streamer@example.com", "streamdb")

    for i in range(len(pkt) - 1):
        conn.send(pkt[i : i + 1])
        assert not captured
        assert not conn.startup_message_sent

    conn.send(pkt[-1:])
    assert captured == [("streamer@example.com", "streamdb")]
    assert conn.startup_message_sent


def test_postgres_connection_prepended_ssl_request_chunked() -> None:
    """Test PostgresConnection handles split SSLRequest followed by StartupMessage."""
    mock_sock = MagicMock()
    mock_sock.sendall = MagicMock()
    captured: list[tuple[str, str]] = []

    conn = PostgresConnection(
        mock_sock,
        on_startup=lambda u, d: captured.append((u, d)),
    )

    ssl_req = b"\x00\x00\x00\x08\x04\xd2\x16\x2f"
    # Split SSLRequest into 4 bytes + 4 bytes
    conn.sendall(ssl_req[:4])
    assert not captured
    conn.sendall(ssl_req[4:])
    assert not captured

    startup = build_postgres_startup_packet("ssl-user@example.com", "ssldb")
    conn.sendall(startup)
    assert captured == [("ssl-user@example.com", "ssldb")]
    assert conn.startup_message_sent


def test_postgres_connection_non_postgres_passthrough() -> None:
    """Test non-Postgres protocol bytes pass through without error or callback."""
    mock_sock = MagicMock()
    mock_sock.write = MagicMock(return_value=8)
    captured: list[tuple[str, str]] = []

    conn = PostgresConnection(
        mock_sock,
        on_startup=lambda u, d: captured.append((u, d)),
    )

    # MySQL handshake response header or arbitrary non-pg bytes
    mysql_bytes = b"\x01\x00\x00\x01\x85\xa6\x03\x00"
    conn.write(mysql_bytes)

    assert not captured
    assert conn.startup_message_sent
    mock_sock.write.assert_called_once_with(mysql_bytes)


def test_postgres_connection_socket_methods() -> None:
    """Test socket delegation methods (close, fileno, __enter__, __exit__, etc.)."""
    mock_sock = MagicMock()
    mock_sock.fileno.return_value = 42
    conn = PostgresConnection(mock_sock, on_startup=lambda u, d: None)

    assert conn.fileno() == 42
    conn.close()
    mock_sock.close.assert_called_once()

    with conn as c:
        assert c is conn


def test_postgres_connection_makefile_captures_startup_message() -> None:
    """Test that makefile('rwb') (used by pg8000) routes writes through PostgresConnection."""
    s1, s2 = socket.socketpair()
    captured: list[tuple[str, str]] = []
    conn = PostgresConnection(
        s1,
        on_startup=lambda u, d: captured.append((u, d)),
    )
    try:
        stream = conn.makefile("rwb")
        assert conn._io_refs == 1
        pkt = build_postgres_startup_packet("pg8000-user@example.com", "pg8000db")

        # Write in chunks via BufferedRWPair (just like pg8000 does)
        stream.write(pkt[:8])
        stream.flush()
        assert not captured
        assert not conn.startup_message_sent

        stream.write(pkt[8:])
        stream.flush()
        assert captured == [("pg8000-user@example.com", "pg8000db")]
        assert conn.startup_message_sent
        assert s2.recv(len(pkt)) == pkt

        stream.close()
        assert conn._io_refs == 0
    finally:
        conn.close()
        s2.close()


def test_postgres_connection_partial_send_no_duplicate_buffer() -> None:
    """Test that partial send() return values only inspect bytes actually written."""
    pkt = build_postgres_startup_packet("partial@example.com", "partialdb")
    mock_sock = MagicMock()
    # First send returns 0 bytes (e.g. partial/unaccepted), second sends 6 bytes,
    # third sends the remaining bytes.
    mock_sock.send.side_effect = [0, 6, len(pkt) - 6]
    captured: list[tuple[str, str]] = []

    conn = PostgresConnection(
        mock_sock,
        on_startup=lambda u, d: captured.append((u, d)),
    )

    assert conn.send(pkt) == 0
    assert not captured
    assert conn.send(pkt) == 6
    assert not captured
    assert conn.send(pkt[6:]) == len(pkt) - 6
    assert captured == [("partial@example.com", "partialdb")]
    assert conn.startup_message_sent


def test_postgres_connection_edge_cases_and_parser_boundaries() -> None:
    """Test parser boundary cases, buffer overflow cap, empty writes, and __exit__ without target method."""
    # User present without database defaults database to user
    user_only_body = b"user\x00onlyuser\x00\x00"
    user_only_pkt = (8 + len(user_only_body)).to_bytes(
        4, byteorder="big"
    ) + b"\x00\x03\x00\x00" + user_only_body
    user, db, complete = parse_postgres_startup_packet(user_only_pkt)
    assert complete
    assert (user, db) == ("onlyuser", "onlyuser")

    # build_postgres_startup_packet defaults empty database to user
    built = build_postgres_startup_packet("onlyuser", "")
    assert parse_postgres_startup_packet(built) == ("onlyuser", "onlyuser", True)

    # Truncated key without null terminator stops parsing cleanly
    trunc_key_body = b"user_without_null"
    trunc_key_pkt = (8 + len(trunc_key_body)).to_bytes(
        4, byteorder="big"
    ) + b"\x00\x03\x00\x00" + trunc_key_body
    assert parse_postgres_startup_packet(trunc_key_pkt) == ("", "", True)

    # Key present, value missing null terminator stops parsing cleanly
    trunc_val_body = b"user\x00val_without_null"
    trunc_val_pkt = (8 + len(trunc_val_body)).to_bytes(
        4, byteorder="big"
    ) + b"\x00\x03\x00\x00" + trunc_val_body
    assert parse_postgres_startup_packet(trunc_val_pkt) == ("", "", True)

    # Exceeding MAX_PG_STARTUP_PACKET_LEN + 16 with repeated SSLRequest disables inspection
    class BareSocket:
        def send(self, data: bytes) -> int:
            return len(data)

    captured: list[tuple[str, str]] = []
    bare_conn = PostgresConnection(
        BareSocket(),  # type: ignore[arg-type]
        on_startup=lambda u, d: captured.append((u, d)),
    )
    bare_conn._inspect(b"")
    ssl_req = b"\x00\x00\x00\x08\x04\xd2\x16\x2f"
    oversized = ssl_req * ((MAX_PG_STARTUP_PACKET_LEN + 16) // 8 + 2)
    bare_conn.send(oversized)
    assert bare_conn.startup_message_sent
    assert bare_conn._buf == bytearray()
    assert not captured

    # __exit__ returns None cleanly when underlying socket lacks __exit__
    with bare_conn as entered:
        assert entered is bare_conn
