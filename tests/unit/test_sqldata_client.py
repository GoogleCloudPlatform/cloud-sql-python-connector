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

from __future__ import annotations

import socket
import time
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from google.auth.credentials import Credentials
import grpc
import pytest

from google.cloud.sql.connector.proto import sql_data_service_pb2
from google.cloud.sql.connector.sqldata_client import _RequestQueue
from google.cloud.sql.connector.sqldata_client import is_resource_exhausted_error
from google.cloud.sql.connector.sqldata_client import SqlDataClient
from google.cloud.sql.connector.sqldata_client import SqlDataSocket


class MockRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode):
        self._code = code

    def code(self) -> grpc.StatusCode:
        return self._code


def test_is_resource_exhausted_error():
    # Regular exception
    assert not is_resource_exhausted_error(ValueError("foo"))

    # RpcError with RESOURCE_EXHAUSTED
    mock_err = MockRpcError(grpc.StatusCode.RESOURCE_EXHAUSTED)
    assert is_resource_exhausted_error(mock_err)

    # RpcError with other status
    mock_err_other = MockRpcError(grpc.StatusCode.UNAVAILABLE)
    assert not is_resource_exhausted_error(mock_err_other)

    # Wrapped exception
    wrapped = Exception("wrapped")
    wrapped.__cause__ = mock_err
    assert is_resource_exhausted_error(wrapped)


def test_sqldata_socket_send_recv():
    mock_response_stream = MagicMock()
    mock_channel = MagicMock()
    req_queue = _RequestQueue()

    data_packet = sql_data_service_pb2.DataPacket(data=b"hello world")
    resp1 = sql_data_service_pb2.StreamSqlDataResponse(data=data_packet)

    def stream_gen():
        yield resp1
        # Block until stream cancelled/closed
        time.sleep(1.0)

    mock_response_stream.__iter__.side_effect = stream_gen

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        channel=mock_channel,
        timeout=2.0,
    )

    # Test sendall
    sock.sendall(b"client query")
    written_req = next(iter(req_queue))
    assert written_req.data.data == b"client query"

    # Test send
    sent_len = sock.send(b"12345")
    assert sent_len == 5

    # Test recv chunked
    chunk1 = sock.recv(5)
    assert chunk1 == b"hello"

    chunk2 = sock.recv(10)
    assert chunk2 == b" world"

    # Test recv_into
    buf = bytearray(5)
    sock._read_queue.put(b"test1")
    n = sock.recv_into(buf)
    assert n == 5
    assert bytes(buf) == b"test1"

    # Test makefile
    sock._read_queue.put(b"line1\nline2\n")
    rfile = sock.makefile("rb")
    line = rfile.readline()
    assert line == b"line1\n"

    # Test socket options & no-ops
    sock.settimeout(5.0)
    assert sock.gettimeout() == 5.0
    sock.setblocking(True)
    assert sock.gettimeout() is None
    sock.connect(("127.0.0.1", 3307))
    assert sock.connect_ex(("127.0.0.1", 3307)) == 0
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    assert sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) == 0
    assert sock.getsockname() == ("127.0.0.1", 3307)
    assert sock.getpeername() == ("127.0.0.1", 3307)

    # Test close
    sock.close()
    assert sock._closed
    with pytest.raises(BrokenPipeError):
        sock.sendall(b"after close")


def test_sqldata_socket_timeout():
    mock_response_stream = MagicMock()
    mock_channel = MagicMock()
    req_queue = _RequestQueue()

    def stream_blocking():
        time.sleep(2.0)
        yield sql_data_service_pb2.StreamSqlDataResponse()

    mock_response_stream.__iter__.side_effect = stream_blocking

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        channel=mock_channel,
        timeout=0.05,
    )

    with pytest.raises(socket.timeout):
        sock.recv(1024)

    sock.close()


@pytest.mark.asyncio
async def test_sqldata_client_connect_success():
    creds = MagicMock(spec=Credentials)
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=creds,
    )

    mock_channel = MagicMock()
    mock_stream = MagicMock()

    def stream_gen():
        time.sleep(1.0)
        yield sql_data_service_pb2.StreamSqlDataResponse()

    mock_stream.__iter__.side_effect = stream_gen

    with patch("grpc.secure_channel", return_value=mock_channel), patch(
        "google.cloud.sql.connector.proto.sql_data_service_pb2_grpc.SqlDataServiceStub"
    ) as mock_stub_cls:
        mock_stub = MagicMock()
        mock_stub.StreamSqlData.return_value = mock_stream
        mock_stub_cls.return_value = mock_stub

        on_success = MagicMock()
        sock = await client.connect(
            instance_connection_name="proj:region:inst",
            region="region",
            project="proj",
            get_conn_info=MagicMock(),
            enable_iam_auth=False,
            on_fallback=MagicMock(),
            is_fallback_cached=lambda _: False,
            on_success=on_success,
        )

        assert isinstance(sock, SqlDataSocket)
        await client.close()
        assert sock._closed


@pytest.mark.asyncio
async def test_sqldata_client_fallback():
    creds = MagicMock(spec=Credentials)
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=creds,
    )

    mock_channel = MagicMock()
    # Simulate stream creation failure triggering fallback
    rpc_err = MockRpcError(grpc.StatusCode.UNAVAILABLE)

    mock_conn_info = MagicMock()
    mock_conn_info.get_preferred_ips.return_value = ["1.2.3.4"]
    mock_ssl_ctx = MagicMock()
    mock_conn_info.create_ssl_context = AsyncMock(
        return_value=mock_ssl_ctx
    )
    get_conn_info = AsyncMock(return_value=mock_conn_info)

    mock_raw_sock = MagicMock(spec=socket.socket)
    mock_ssl_sock = MagicMock(spec=socket.socket)
    mock_ssl_ctx.wrap_socket.return_value = mock_ssl_sock

    on_fallback = MagicMock()

    with patch("grpc.secure_channel", return_value=mock_channel), patch(
        "google.cloud.sql.connector.proto.sql_data_service_pb2_grpc.SqlDataServiceStub"
    ) as mock_stub_cls, patch(
        "socket.create_connection", return_value=mock_raw_sock
    ):
        mock_stub = MagicMock()
        mock_stub.StreamSqlData.side_effect = rpc_err
        mock_stub_cls.return_value = mock_stub

        sock = await client.connect(
            instance_connection_name="proj:region:inst",
            region="region",
            project="proj",
            get_conn_info=get_conn_info,
            enable_iam_auth=False,
            on_fallback=on_fallback,
            is_fallback_cached=lambda _: False,
        )

        assert sock is mock_ssl_sock
        assert on_fallback.called
        await client.close()
