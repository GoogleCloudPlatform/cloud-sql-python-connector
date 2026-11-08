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

import asyncio
from dataclasses import dataclass
import datetime
import ipaddress
import json
import os
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.types import CertificatePublicKeyTypes
from cryptography.x509.oid import NameOID
import pytest

from google.cloud.sql.connector.connection_info import ConnectionInfo
from google.cloud.sql.connector.connection_name import ConnectionName
from google.cloud.sql.connector.utils import AsyncTemporaryDirectory
from google.cloud.sql.connector.utils import generate_keys
from google.cloud.sql.connector.utils import write_to_file

# IANA TLS NamedGroup identifiers (RFC 8446 / draft-ietf-tls-ecdhe-mlkem)
SECP256R1_GROUP_ID = 0x0017
X25519_GROUP_ID = 0x001D
X25519_MLKEM768_GROUP_ID = 0x11EC

# RFC 8446 Section 4.1.3 HelloRetryRequest special ServerHello.random value
_HRR_RANDOM = bytes.fromhex(
    "CF21AD74E59A6111BE1D8C021E65B891C2A211167ABB8C5E079E09E2C8A8339C"
)

_EXT_SUPPORTED_GROUPS = 0x000A
_EXT_KEY_SHARE = 0x0033


@dataclass
class HandshakeCapture:
    """Captured wire-level TLS 1.3 handshake metadata and negotiated parameters."""

    tls_version: str | None
    cipher: tuple[str, str, int] | None
    client_supported_groups: list[int]
    client_initial_key_shares: list[int]
    server_selected_group: int | None
    saw_hello_retry_request: bool


class _TestMTLSAuthority:
    """Test CA and server certificate bundle supporting strict OpenSSL 3.x mTLS."""

    def __init__(self) -> None:
        now = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)
        expires = now + datetime.timedelta(hours=2)
        self._not_before = now
        self._not_after = expires

        self.ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.ca_subject = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Google Inc"),
                x509.NameAttribute(NameOID.COMMON_NAME, "Cloud SQL Test Root CA"),
            ]
        )
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(self.ca_subject)
            .issuer_name(self.ca_subject)
            .public_key(self.ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(expires)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(self.ca_key.public_key()),
                False,
            )
            .sign(self.ca_key, hashes.SHA256())
        )
        self.ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode(
            "UTF-8"
        )

        self.server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        server_subject = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Google Inc"),
                x509.NameAttribute(NameOID.COMMON_NAME, "test-project:test-instance"),
            ]
        )
        server_cert = (
            x509.CertificateBuilder()
            .subject_name(server_subject)
            .issuer_name(self.ca_subject)
            .public_key(self.server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(expires)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
                ),
                False,
            )
            .sign(self.ca_key, hashes.SHA256())
        )
        self.server_cert_pem = server_cert.public_bytes(
            serialization.Encoding.PEM
        ).decode("UTF-8")
        self.server_key_pem = self.server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def sign_client_cert(self, client_pub_key: CertificatePublicKeyTypes) -> str:
        """Issue an ephemeral client certificate signed by the test CA."""
        client_subject = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Google Inc"),
                x509.NameAttribute(NameOID.COMMON_NAME, "Google Cloud SQL Client"),
            ]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(client_subject)
            .issuer_name(self.ca_subject)
            .public_key(client_pub_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(self._not_before)
            .not_valid_after(self._not_after)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .sign(self.ca_key, hashes.SHA256())
        )
        return cert.public_bytes(serialization.Encoding.PEM).decode("UTF-8")

    async def build_server_ssl_context(
        self, ecdh_curve: str | None = None
    ) -> ssl.SSLContext:
        """Construct a TLS 1.3 mTLS server SSLContext requiring client certs."""
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        server_ctx.verify_mode = ssl.CERT_REQUIRED
        if ecdh_curve is not None:
            server_ctx.set_ecdh_curve(ecdh_curve)

        async with AsyncTemporaryDirectory() as tmpdir:
            ca_file, cert_file, key_file = await write_to_file(
                tmpdir, self.ca_cert_pem, self.server_cert_pem, self.server_key_pem
            )
            server_ctx.load_cert_chain(cert_file, keyfile=key_file)
            server_ctx.load_verify_locations(cafile=ca_file)
        return server_ctx

    def make_connection_info(
        self, priv_key_pem: bytes, pub_key_pem: str
    ) -> ConnectionInfo:
        """Build a ConnectionInfo populated with a CA-signed client certificate."""
        client_pub: CertificatePublicKeyTypes = serialization.load_pem_public_key(
            pub_key_pem.encode("UTF-8")
        )  # type: ignore[assignment]
        ephemeral_cert = self.sign_client_cert(client_pub)
        return ConnectionInfo(
            conn_name=ConnectionName("test-project", "test-region", "test-instance"),
            client_cert=ephemeral_cert,
            server_ca_cert=self.ca_cert_pem,
            private_key=priv_key_pem,
            ip_addrs={"PRIMARY": ["127.0.0.1"]},
            database_version="POSTGRES_15",
            expiration=self._not_after,
        )


@pytest.fixture(scope="module")
def mtls_authority() -> _TestMTLSAuthority:
    return _TestMTLSAuthority()


def _extract_plaintext_handshake_bytes(raw_stream: bytes) -> bytes:
    """Extract concatenated TLS Handshake (content_type=22) record payloads."""
    out = bytearray()
    offset = 0
    total = len(raw_stream)
    while offset + 5 <= total:
        content_type = raw_stream[offset]
        record_len = struct.unpack_from("!H", raw_stream, offset + 3)[0]
        offset += 5
        if offset + record_len > total:
            break
        if content_type == 22:
            out.extend(raw_stream[offset : offset + record_len])
        offset += record_len
    return bytes(out)


def _iter_handshake_messages(hs_stream: bytes) -> list[tuple[int, bytes]]:
    """Parse TLS handshake messages into (msg_type, body) tuples."""
    messages: list[tuple[int, bytes]] = []
    pos = 0
    total = len(hs_stream)
    while pos + 4 <= total:
        msg_type = hs_stream[pos]
        msg_len = int.from_bytes(hs_stream[pos + 1 : pos + 4], "big")
        pos += 4
        if pos + msg_len > total:
            break
        messages.append((msg_type, hs_stream[pos : pos + msg_len]))
        pos += msg_len
    return messages


def _parse_client_hello(body: bytes) -> tuple[list[int], list[int]]:
    """Return (supported_groups, key_share_groups) from a ClientHello body."""
    supported_groups: list[int] = []
    key_shares: list[int] = []

    # legacy_version (2) + random (32)
    idx = 34
    session_id_len = body[idx]
    idx += 1 + session_id_len
    cipher_suites_len = struct.unpack_from("!H", body, idx)[0]
    idx += 2 + cipher_suites_len
    comp_methods_len = body[idx]
    idx += 1 + comp_methods_len
    if idx + 2 > len(body):
        return supported_groups, key_shares

    ext_total_len = struct.unpack_from("!H", body, idx)[0]
    idx += 2
    end_ext = min(idx + ext_total_len, len(body))

    while idx + 4 <= end_ext:
        ext_type, ext_len = struct.unpack_from("!HH", body, idx)
        idx += 4
        ext_data = body[idx : idx + ext_len]
        idx += ext_len

        if ext_type == _EXT_SUPPORTED_GROUPS and len(ext_data) >= 2:
            list_len = struct.unpack_from("!H", ext_data, 0)[0]
            for pos in range(2, min(2 + list_len, len(ext_data)), 2):
                supported_groups.append(struct.unpack_from("!H", ext_data, pos)[0])
        elif ext_type == _EXT_KEY_SHARE and len(ext_data) >= 2:
            shares_len = struct.unpack_from("!H", ext_data, 0)[0]
            pos = 2
            limit = min(2 + shares_len, len(ext_data))
            while pos + 4 <= limit:
                group, kex_len = struct.unpack_from("!HH", ext_data, pos)
                key_shares.append(group)
                pos += 4 + kex_len

    return supported_groups, key_shares


def _parse_server_hello(body: bytes) -> tuple[bool, int | None]:
    """Return (is_hello_retry_request, key_share_group) from a ServerHello body."""
    server_random = body[2:34]
    is_hrr = server_random == _HRR_RANDOM

    idx = 34
    session_id_len = body[idx]
    idx += 1 + session_id_len
    # cipher_suite (2) + legacy_compression_method (1)
    idx += 3
    if idx + 2 > len(body):
        return is_hrr, None

    ext_total_len = struct.unpack_from("!H", body, idx)[0]
    idx += 2
    end_ext = min(idx + ext_total_len, len(body))

    selected_group: int | None = None
    while idx + 4 <= end_ext:
        ext_type, ext_len = struct.unpack_from("!HH", body, idx)
        idx += 4
        ext_data = body[idx : idx + ext_len]
        idx += ext_len
        if ext_type == _EXT_KEY_SHARE and len(ext_data) >= 2:
            selected_group = struct.unpack_from("!H", ext_data, 0)[0]

    return is_hrr, selected_group


def _relay_stream(src: socket.socket, dst: socket.socket, captured: bytearray) -> None:
    """Forward TCP bytes from src to dst while recording raw TLS records."""
    try:
        while True:
            chunk = src.recv(16384)
            if not chunk:
                break
            captured.extend(chunk)
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _run_mtls_handshake_with_wire_capture(
    client_ctx: ssl.SSLContext,
    server_ctx: ssl.SSLContext,
) -> HandshakeCapture:
    """Execute a real socket TLS 1.3 mTLS handshake through a local TCP capture relay."""
    c2s_bytes = bytearray()
    s2c_bytes = bytearray()
    server_errors: list[BaseException] = []

    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_listener,
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as proxy_listener,
    ):
        server_listener.settimeout(10)
        server_listener.bind(("127.0.0.1", 0))
        server_listener.listen(1)
        server_addr = server_listener.getsockname()

        proxy_listener.settimeout(10)
        proxy_listener.bind(("127.0.0.1", 0))
        proxy_listener.listen(1)
        proxy_addr = proxy_listener.getsockname()

        def run_server() -> None:
            try:
                raw_conn, _ = server_listener.accept()
                raw_conn.settimeout(10)
                with (
                    raw_conn,
                    server_ctx.wrap_socket(raw_conn, server_side=True) as tls_conn,
                ):
                    data = tls_conn.recv(64)
                    assert data == b"pqc-ping"
                    assert tls_conn.getpeercert() is not None
                    tls_conn.sendall(b"pqc-pong")
            except (OSError, ssl.SSLError, AssertionError) as exc:  # pragma: no cover
                server_errors.append(exc)

        def run_proxy() -> None:
            client_side, _ = proxy_listener.accept()
            client_side.settimeout(10)
            server_side = socket.create_connection(server_addr, timeout=10)
            t_up = threading.Thread(
                target=_relay_stream,
                args=(client_side, server_side, c2s_bytes),
                daemon=True,
            )
            t_down = threading.Thread(
                target=_relay_stream,
                args=(server_side, client_side, s2c_bytes),
                daemon=True,
            )
            t_up.start()
            t_down.start()
            t_up.join(timeout=10)
            t_down.join(timeout=10)
            client_side.close()
            server_side.close()

        server_thread = threading.Thread(target=run_server, daemon=True)
        proxy_thread = threading.Thread(target=run_proxy, daemon=True)
        server_thread.start()
        proxy_thread.start()

        with (
            socket.create_connection(proxy_addr, timeout=10) as raw_client,
            client_ctx.wrap_socket(raw_client) as tls_client,
        ):
            tls_version = tls_client.version()
            cipher = tls_client.cipher()
            tls_client.sendall(b"pqc-ping")
            reply = tls_client.recv(64)
            assert reply == b"pqc-pong"

        server_thread.join(timeout=10)
        proxy_thread.join(timeout=10)

    if server_errors:
        raise server_errors[0]

    c2s_hs = _extract_plaintext_handshake_bytes(bytes(c2s_bytes))
    s2c_hs = _extract_plaintext_handshake_bytes(bytes(s2c_bytes))

    client_msgs = [
        body for msg_type, body in _iter_handshake_messages(c2s_hs) if msg_type == 1
    ]
    server_msgs = [
        body for msg_type, body in _iter_handshake_messages(s2c_hs) if msg_type == 2
    ]
    assert len(client_msgs) >= 1, "Expected at least one TLS ClientHello message"
    assert len(server_msgs) >= 1, "Expected at least one TLS ServerHello message"

    supported_groups, initial_key_shares = _parse_client_hello(client_msgs[0])
    saw_hrr = False
    selected_group: int | None = None
    for sh_body in server_msgs:
        is_hrr, group = _parse_server_hello(sh_body)
        if is_hrr:
            saw_hrr = True
        else:
            selected_group = group

    return HandshakeCapture(
        tls_version=tls_version,
        cipher=cipher,
        client_supported_groups=supported_groups,
        client_initial_key_shares=initial_key_shares,
        server_selected_group=selected_group,
        saw_hello_retry_request=saw_hrr,
    )


@pytest.mark.asyncio
async def test_create_ssl_context_pkcs8_and_legacy_pkcs1_mtls(
    mtls_authority: _TestMTLSAuthority,
) -> None:
    """Verify ConnectionInfo.create_ssl_context() succeeds over TLS 1.3 mTLS
    with both modern PKCS#8 keys (from generate_keys()) and legacy PKCS#1 RSA keys."""
    server_ctx = await mtls_authority.build_server_ssl_context()

    # 1. Default generate_keys() -> PKCS#8 PEM
    pkcs8_priv, spki_pub = await generate_keys()
    assert pkcs8_priv.startswith(b"-----BEGIN PRIVATE KEY-----\n")
    pkcs8_info = mtls_authority.make_connection_info(pkcs8_priv, spki_pub)
    pkcs8_ctx = await pkcs8_info.create_ssl_context()
    assert pkcs8_ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    capture_pkcs8 = await asyncio.to_thread(
        _run_mtls_handshake_with_wire_capture, pkcs8_ctx, server_ctx
    )
    assert capture_pkcs8.tls_version == "TLSv1.3"

    # 2. Backwards compatibility: legacy PKCS#1 (TraditionalOpenSSL) RSA key
    legacy_rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pkcs1_priv = legacy_rsa.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    assert pkcs1_priv.startswith(b"-----BEGIN RSA PRIVATE KEY-----\n")
    legacy_pub = (
        legacy_rsa.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("UTF-8")
    )
    pkcs1_info = mtls_authority.make_connection_info(pkcs1_priv, legacy_pub)
    pkcs1_ctx = await pkcs1_info.create_ssl_context()

    capture_pkcs1 = await asyncio.to_thread(
        _run_mtls_handshake_with_wire_capture, pkcs1_ctx, server_ctx
    )
    assert capture_pkcs1.tls_version == "TLSv1.3"


@pytest.mark.asyncio
async def test_create_ssl_context_algorithm_agnostic_ecdsa_pkcs8(
    mtls_authority: _TestMTLSAuthority,
) -> None:
    """Verify PKCS#8 PEM handling in ConnectionInfo is algorithm-agnostic
    (non-RSA ECDSA client keys work end-to-end over TLS 1.3 mTLS)."""
    server_ctx = await mtls_authority.build_server_ssl_context()

    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_priv_pkcs8 = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    ec_pub_spki = (
        ec_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("UTF-8")
    )
    ec_info = mtls_authority.make_connection_info(ec_priv_pkcs8, ec_pub_spki)
    ec_ctx = await ec_info.create_ssl_context()

    capture = await asyncio.to_thread(
        _run_mtls_handshake_with_wire_capture, ec_ctx, server_ctx
    )
    assert capture.tls_version == "TLSv1.3"


@pytest.mark.skipif(
    ssl.OPENSSL_VERSION_INFO < (3, 5, 0),
    reason=f"X25519MLKEM768 requires OpenSSL 3.5+, got {ssl.OPENSSL_VERSION}",
)
@pytest.mark.asyncio
async def test_tls13_pqc_x25519mlkem768_handshake(
    mtls_authority: _TestMTLSAuthority,
) -> None:
    """Verify ConnectionInfo.create_ssl_context() offers and negotiates hybrid
    post-quantum key exchange X25519MLKEM768 (0x11ec) by default on OpenSSL 3.5+."""
    priv_pem, pub_pem = await generate_keys()
    conn_info = mtls_authority.make_connection_info(priv_pem, pub_pem)
    client_ctx = await conn_info.create_ssl_context()
    server_ctx = await mtls_authority.build_server_ssl_context()

    capture = await asyncio.to_thread(
        _run_mtls_handshake_with_wire_capture, client_ctx, server_ctx
    )

    assert capture.tls_version == "TLSv1.3"
    assert X25519_MLKEM768_GROUP_ID in capture.client_supported_groups, (
        f"Expected X25519MLKEM768 (0x11ec) in ClientHello supported_groups, "
        f"got {[hex(g) for g in capture.client_supported_groups]}"
    )
    assert X25519_MLKEM768_GROUP_ID in capture.client_initial_key_shares, (
        f"Expected X25519MLKEM768 (0x11ec) in ClientHello key_share, "
        f"got {[hex(g) for g in capture.client_initial_key_shares]}"
    )
    assert capture.server_selected_group == X25519_MLKEM768_GROUP_ID, (
        f"Expected negotiated ServerHello group X25519MLKEM768 (0x11ec), "
        f"got {hex(capture.server_selected_group) if capture.server_selected_group else None}"
    )
    assert capture.saw_hello_retry_request is False


@pytest.mark.asyncio
async def test_tls13_classical_fallback_handshake(
    mtls_authority: _TestMTLSAuthority,
) -> None:
    """Verify ConnectionInfo.create_ssl_context() cleanly falls back to classical
    ECDHE (secp256r1 / 0x0017) when the server only offers classical groups."""
    priv_pem, pub_pem = await generate_keys()
    conn_info = mtls_authority.make_connection_info(priv_pem, pub_pem)
    client_ctx = await conn_info.create_ssl_context()
    # Restrict server to classical P-256 only
    server_ctx = await mtls_authority.build_server_ssl_context(ecdh_curve="prime256v1")

    capture = await asyncio.to_thread(
        _run_mtls_handshake_with_wire_capture, client_ctx, server_ctx
    )

    assert capture.tls_version == "TLSv1.3"
    assert SECP256R1_GROUP_ID in capture.client_supported_groups
    assert capture.server_selected_group == SECP256R1_GROUP_ID
    if ssl.OPENSSL_VERSION_INFO >= (3, 5, 0):
        # Client offered X25519MLKEM768 first and fell back via HelloRetryRequest
        assert X25519_MLKEM768_GROUP_ID in capture.client_initial_key_shares
        assert capture.saw_hello_retry_request is True


def _run_opt_out_subprocess_handshake(
    conn_info: ConnectionInfo,
    priv_pem: bytes,
    server_ctx: ssl.SSLContext,
) -> tuple[list[int], list[int], int | None]:
    """Run a subprocess client with OPENSSL_CONF classical Groups opt-out."""
    c2s_bytes = bytearray()
    s2c_bytes = bytearray()
    server_errors: list[Exception] = []

    with (
        tempfile.TemporaryDirectory() as tmpdir,
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_listener,
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as proxy_listener,
    ):
        openssl_cnf = os.path.join(tmpdir, "openssl.cnf")
        with open(openssl_cnf, "w", encoding="UTF-8") as f:
            f.write(
                "openssl_conf = openssl_init\n"
                "[openssl_init]\n"
                "ssl_conf = ssl_sect\n"
                "[ssl_sect]\n"
                "system_default = system_default_sect\n"
                "[system_default_sect]\n"
                "Groups = X25519:P-256:P-384\n"
            )

        payload_path = os.path.join(tmpdir, "conn_payload.json")
        server_listener.settimeout(10)
        server_listener.bind(("127.0.0.1", 0))
        server_listener.listen(1)
        server_addr = server_listener.getsockname()

        proxy_listener.settimeout(10)
        proxy_listener.bind(("127.0.0.1", 0))
        proxy_listener.listen(1)
        proxy_addr = proxy_listener.getsockname()

        with open(payload_path, "w", encoding="UTF-8") as f:
            json.dump(
                {
                    "host": proxy_addr[0],
                    "port": proxy_addr[1],
                    "client_cert": conn_info.client_cert,
                    "server_ca_cert": conn_info.server_ca_cert,
                    "private_key": priv_pem.decode("UTF-8"),
                },
                f,
            )

        def run_server() -> None:
            try:
                raw_conn, _ = server_listener.accept()
                raw_conn.settimeout(10)
                with (
                    raw_conn,
                    server_ctx.wrap_socket(raw_conn, server_side=True) as tls_conn,
                ):
                    assert tls_conn.recv(64) == b"optout-ping"
                    assert tls_conn.getpeercert() is not None
                    tls_conn.sendall(b"optout-pong")
            except (OSError, ssl.SSLError, AssertionError) as exc:  # pragma: no cover
                server_errors.append(exc)

        def run_proxy() -> None:
            client_side, _ = proxy_listener.accept()
            client_side.settimeout(10)
            server_side = socket.create_connection(server_addr, timeout=10)
            t_up = threading.Thread(
                target=_relay_stream,
                args=(client_side, server_side, c2s_bytes),
                daemon=True,
            )
            t_down = threading.Thread(
                target=_relay_stream,
                args=(server_side, client_side, s2c_bytes),
                daemon=True,
            )
            t_up.start()
            t_down.start()
            t_up.join(timeout=10)
            t_down.join(timeout=10)
            client_side.close()
            server_side.close()

        server_thread = threading.Thread(target=run_server, daemon=True)
        proxy_thread = threading.Thread(target=run_proxy, daemon=True)
        server_thread.start()
        proxy_thread.start()

        child_code = (
            "import asyncio, datetime, json, socket, sys\n"
            "from google.cloud.sql.connector.connection_info import ConnectionInfo\n"
            "from google.cloud.sql.connector.connection_name import ConnectionName\n"
            "async def main(path: str) -> None:\n"
            "    data = json.load(open(path, encoding='utf-8'))\n"
            "    info = ConnectionInfo(\n"
            "        ConnectionName('p', 'r', 'i'),\n"
            "        data['client_cert'],\n"
            "        data['server_ca_cert'],\n"
            "        data['private_key'].encode('utf-8'),\n"
            "        {'PRIMARY': ['127.0.0.1']},\n"
            "        'POSTGRES_15',\n"
            "        datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),\n"
            "    )\n"
            "    ctx = await info.create_ssl_context()\n"
            "    with socket.create_connection((data['host'], data['port']), timeout=10) as s:\n"
            "        with ctx.wrap_socket(s) as ts:\n"
            "            assert ts.version() == 'TLSv1.3'\n"
            "            ts.sendall(b'optout-ping')\n"
            "            assert ts.recv(64) == b'optout-pong'\n"
            "asyncio.run(main(sys.argv[1]))\n"
        )
        env: dict[str, Any] = os.environ.copy()
        env["OPENSSL_CONF"] = openssl_cnf
        subprocess.run(
            [sys.executable, "-c", child_code, payload_path],
            env=env,
            check=True,
            timeout=15,
        )

        server_thread.join(timeout=10)
        proxy_thread.join(timeout=10)

    if server_errors:
        raise server_errors[0]

    c2s_hs = _extract_plaintext_handshake_bytes(bytes(c2s_bytes))
    s2c_hs = _extract_plaintext_handshake_bytes(bytes(s2c_bytes))
    client_msgs = [b for t, b in _iter_handshake_messages(c2s_hs) if t == 1]
    server_msgs = [b for t, b in _iter_handshake_messages(s2c_hs) if t == 2]

    supported_groups, initial_key_shares = _parse_client_hello(client_msgs[0])
    _, selected_group = _parse_server_hello(server_msgs[-1])
    return supported_groups, initial_key_shares, selected_group


@pytest.mark.skipif(
    ssl.OPENSSL_VERSION_INFO < (3, 5, 0),
    reason=f"OpenSSL 3.5+ PQC opt-out test requires OpenSSL >= 3.5, got {ssl.OPENSSL_VERSION}",
)
@pytest.mark.asyncio
async def test_tls13_client_opt_out_openssl_conf(
    mtls_authority: _TestMTLSAuthority,
) -> None:
    """Verify client-side PQC opt-out via OPENSSL_CONF Groups=X25519:P-256:P-384
    omits X25519MLKEM768 from ClientHello and negotiates classical X25519."""
    priv_pem, pub_pem = await generate_keys()
    conn_info = mtls_authority.make_connection_info(priv_pem, pub_pem)
    server_ctx = await mtls_authority.build_server_ssl_context()

    (
        supported_groups,
        initial_key_shares,
        selected_group,
    ) = await asyncio.to_thread(
        _run_opt_out_subprocess_handshake, conn_info, priv_pem, server_ctx
    )

    assert X25519_MLKEM768_GROUP_ID not in supported_groups
    assert X25519_MLKEM768_GROUP_ID not in initial_key_shares
    assert selected_group == X25519_GROUP_ID
