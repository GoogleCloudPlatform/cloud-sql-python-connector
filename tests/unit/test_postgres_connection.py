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

from unittest.mock import MagicMock

from google.cloud.sql.connector.postgres_connection import build_postgres_startup_packet
from google.cloud.sql.connector.postgres_connection import build_terminate_packet
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
