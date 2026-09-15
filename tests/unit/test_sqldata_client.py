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

from google.api_core.exceptions import ResourceExhausted
from google.auth.credentials import Credentials
import grpc
import pytest

from google.cloud import sqladmin_v1beta4
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

    # ResourceExhausted from google.api_core.exceptions
    assert is_resource_exhausted_error(ResourceExhausted("quota exceeded"))

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
    mock_grpc_client = MagicMock()
    req_queue = _RequestQueue()

    data_packet = sqladmin_v1beta4.DataPacket(data=b"hello world")
    resp1 = sqladmin_v1beta4.StreamSqlDataResponse(data=data_packet)

    def stream_gen():
        yield resp1
        # Block until stream cancelled/closed
        time.sleep(1.0)

    mock_response_stream.__iter__.side_effect = stream_gen

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
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

    # Test recv_into
    buf = bytearray(5)
    n = sock.recv_into(buf)
    assert n == 5
    assert bytes(buf) == b" worl"

    # Test makefile
    sock._read_queue.put(b"line1\nline2\n")
    rfile = sock.makefile("rb")
    line = rfile.readline()
    assert line == b"dline1\n" or line == b"line1\n" or line.endswith(b"line1\n")

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



def test_is_resource_exhausted_error_code_exception():
    class BrokenError(Exception):
        def code(self):
            raise RuntimeError("code failed")

    err = BrokenError()
    assert not is_resource_exhausted_error(err)

    # Wrapped with code exception in parent but valid in cause
    wrapped = Exception("wrapper")
    wrapped.__cause__ = MockRpcError(grpc.StatusCode.RESOURCE_EXHAUSTED)
    err.__cause__ = wrapped
    assert is_resource_exhausted_error(err)


def test_request_queue_operations():
    q = _RequestQueue()
    q.put("item1")
    assert next(q) == "item1"

    q.close()
    # Second close should be a no-op
    q.close()

    # Next after close should raise StopIteration
    with pytest.raises(StopIteration):
        next(q)

    # Put after close should raise BrokenPipeError
    with pytest.raises(BrokenPipeError):
        q.put("item2")


def test_sqldata_raw_io():
    mock_sock = MagicMock(spec=SqlDataSocket)
    mock_sock.recv_into.return_value = 4
    mock_sock.closed = False
    mock_sock.makefile(buffering=0)

    from google.cloud.sql.connector.sqldata_client import SqlDataRawIO


    raw_io = SqlDataRawIO(mock_sock)
    assert raw_io.readable() is True
    assert raw_io.writable() is True
    assert raw_io.seekable() is False

    buf = bytearray(10)
    assert raw_io.readinto(buf) == 4
    mock_sock.recv_into.assert_called_once_with(buf)

    assert raw_io.write(b"data") == 4
    mock_sock.sendall.assert_called_once_with(b"data")

    raw_io.close()
    mock_sock.close.assert_called_once()


def test_sqldata_socket_direct_sock_delegation():
    mock_response_stream = MagicMock()
    mock_grpc_client = MagicMock()
    req_queue = _RequestQueue()

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
    )
    mock_direct = MagicMock(spec=socket.socket)
    sock._direct_sock = mock_direct

    mock_direct.send.return_value = 4
    mock_direct.recv.return_value = b"resp"
    mock_direct.recv_into.return_value = 4
    mock_direct.makefile.return_value = MagicMock()
    mock_direct.gettimeout.return_value = 12.0
    mock_direct.getsockopt.return_value = 1
    mock_direct.getsockname.return_value = ("10.0.0.1", 3307)
    mock_direct.getpeername.return_value = ("10.0.0.2", 3307)

    sock.sendall(b"test")
    mock_direct.sendall.assert_called_once_with(b"test", 0)

    assert sock.send(b"test") == 4
    mock_direct.send.assert_called_once_with(b"test", 0)

    assert sock.recv(1024) == b"resp"
    mock_direct.recv.assert_called_once_with(1024, 0)

    buf = bytearray(10)
    assert sock.recv_into(buf) == 4
    mock_direct.recv_into.assert_called_once_with(buf, 0, 0)


    sock.makefile("r")
    mock_direct.makefile.assert_called_once()

    sock.settimeout(12.0)
    mock_direct.settimeout.assert_called_once_with(12.0)
    assert sock.gettimeout() == 12.0

    sock.setblocking(False)
    mock_direct.setblocking.assert_called_once_with(False)

    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    mock_direct.setsockopt.assert_called_once_with(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    assert sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) == 1
    assert sock.getsockname() == ("10.0.0.1", 3307)
    assert sock.getpeername() == ("10.0.0.2", 3307)

    sock.shutdown()
    assert sock._closed


def test_sqldata_socket_makefile_modes():
    mock_response_stream = MagicMock()
    mock_grpc_client = MagicMock()
    req_queue = _RequestQueue()

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
    )

    # Unbuffered binary raw mode
    f_raw = sock.makefile(mode="rb", buffering=0)
    assert hasattr(f_raw, "readinto")

    # Buffered write mode
    f_write = sock.makefile(mode="wb")
    assert hasattr(f_write, "write")

    # Buffered read/write mode
    f_rw = sock.makefile(mode="r+b")
    assert hasattr(f_rw, "read")
    assert hasattr(f_rw, "write")

    # Text read mode
    f_text = sock.makefile(mode="r", encoding="utf-8")
    assert hasattr(f_text, "readline")

    sock.close()


def test_sqldata_socket_edge_cases():
    mock_response_stream = MagicMock()
    mock_grpc_client = MagicMock()
    req_queue = _RequestQueue()

    on_close_called = False

    def on_close():
        nonlocal on_close_called
        on_close_called = True
        raise RuntimeError("on_close error")

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
        on_close=on_close,
    )

    # sendall with empty bytes
    sock.sendall(b"")

    # recv with non-positive bufsize
    assert sock.recv(0) == b""
    assert sock.recv(-1) == b""

    # recv_into with 0 bytes
    buf = bytearray(0)
    assert sock.recv_into(buf) == 0

    # Negative timeout
    with pytest.raises(ValueError):
        sock.settimeout(-1.0)

    # Exception in transport.close and stream.cancel handled cleanly
    mock_grpc_client.transport.close.side_effect = RuntimeError("transport close error")
    mock_response_stream.cancel.side_effect = RuntimeError("cancel error")

    sock.close()
    assert on_close_called is True
    # Calling close again is idempotent
    sock.close()

    # Recv after closed returns empty bytes
    assert sock.recv(10) == b""


def test_sqldata_socket_reader_loop_messages():
    mock_response_stream = MagicMock()
    mock_grpc_client = MagicMock()
    req_queue = _RequestQueue()

    # Test session_metadata and terminate_session
    resp_meta = sqladmin_v1beta4.StreamSqlDataResponse(
        session_metadata=sqladmin_v1beta4.SessionMetadata()
    )
    resp_term = sqladmin_v1beta4.StreamSqlDataResponse(
        terminate_session=sqladmin_v1beta4.TerminateSession()
    )

    def stream_messages():
        yield resp_meta
        yield resp_term

    mock_response_stream.__iter__.side_effect = stream_messages

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
        on_success=MagicMock(),
    )

    time.sleep(0.1)
    assert sock._closed is True
    sock.close()


def test_sqldata_socket_reader_loop_resource_exhausted():
    mock_response_stream = MagicMock()
    mock_grpc_client = MagicMock()
    req_queue = _RequestQueue()

    def stream_err():
        time.sleep(0.01)
        raise MockRpcError(grpc.StatusCode.RESOURCE_EXHAUSTED)
        yield

    mock_response_stream.__iter__.side_effect = stream_err

    resource_exhausted_called = False

    def on_res_exhausted(err):
        nonlocal resource_exhausted_called
        resource_exhausted_called = True

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
        on_resource_exhausted=on_res_exhausted,
    )

    time.sleep(0.1)
    assert resource_exhausted_called is True

    # Recv without fallback raises OSError
    with pytest.raises(OSError) as exc_info:
        sock.recv(10)
    assert exc_info.value.errno == 104  # ECONNRESET
    sock.close()


def test_sqldata_socket_fallback_error_propagation():
    mock_response_stream = MagicMock()
    mock_grpc_client = MagicMock()
    req_queue = _RequestQueue()

    def stream_err():
        time.sleep(0.01)
        raise MockRpcError(grpc.StatusCode.UNAVAILABLE)
        yield

    mock_response_stream.__iter__.side_effect = stream_err

    def broken_fallback():
        raise RuntimeError("fallback failed")

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
        fallback_fn=broken_fallback,
    )

    with pytest.raises(RuntimeError, match="fallback failed"):
        sock.recv(1024)

    sock.close()


@pytest.mark.asyncio
async def test_sqldata_client_quota_project_metadata():
    creds = MagicMock(spec=Credentials)
    creds.quota_project_id = "cred-quota"
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=creds,
        quota_project="custom-quota",
    )

    mock_grpc_client = MagicMock()
    mock_grpc_client.transport.stream_sql_data = mock_grpc_client.stream_sql_data
    mock_stream = MagicMock()

    def stream_gen():
        time.sleep(0.5)
        yield sqladmin_v1beta4.StreamSqlDataResponse()

    mock_stream.__iter__.side_effect = stream_gen
    mock_grpc_client.stream_sql_data.return_value = mock_stream

    with patch(
        "google.cloud.sqladmin_v1beta4.SqlDataServiceClient",
        return_value=mock_grpc_client,
    ) as mock_client_cls:
        await client.connect(
            instance_connection_name="proj:region:inst",
            region="region",
            project="proj",
            get_conn_info=MagicMock(),
            enable_iam_auth=False,
            on_fallback=MagicMock(),
            is_fallback_cached=lambda _: False,
        )

        # Check ClientOptions had quota_project_id
        client_options = mock_client_cls.call_args[1]["client_options"]
        assert client_options.quota_project_id == "custom-quota"

        # Check metadata included x-goog-request-params
        metadata = mock_grpc_client.stream_sql_data.call_args[1]["metadata"]
        assert any(k == "x-goog-request-params" for k, _ in metadata)

        await client.close()


@pytest.mark.asyncio
async def test_sqldata_client_cached_fallback_connect():
    creds = MagicMock(spec=Credentials)
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=creds,
    )

    mock_conn_info = MagicMock()
    mock_conn_info.get_preferred_ips.return_value = ["10.0.0.1"]
    mock_ssl_ctx = MagicMock()
    mock_conn_info.create_ssl_context = AsyncMock(return_value=mock_ssl_ctx)
    get_conn_info = AsyncMock(return_value=mock_conn_info)

    mock_raw_sock = MagicMock(spec=socket.socket)
    mock_ssl_sock = MagicMock(spec=socket.socket)
    mock_ssl_ctx.wrap_socket.return_value = mock_ssl_sock

    with patch("socket.create_connection", return_value=mock_raw_sock):
        sock = await client.connect(
            instance_connection_name="proj:region:inst",
            region="region",
            project="proj",
            get_conn_info=get_conn_info,
            enable_iam_auth=False,
            on_fallback=MagicMock(),
            is_fallback_cached=lambda _: True,
        )
        assert sock is mock_ssl_sock
        await client.close()


@pytest.mark.asyncio
async def test_sqldata_client_direct_socket_factory_no_ips():
    creds = MagicMock(spec=Credentials)
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=creds,
    )

    from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError

    mock_conn_info = MagicMock()
    mock_conn_info.get_preferred_ips.side_effect = CloudSQLIPTypeError("no ips")
    get_conn_info = AsyncMock(return_value=mock_conn_info)

    mock_grpc_client = MagicMock()
    mock_grpc_client.transport.stream_sql_data = mock_grpc_client.stream_sql_data
    mock_grpc_client.stream_sql_data.side_effect = MockRpcError(grpc.StatusCode.UNAVAILABLE)

    with (
        patch(
            "google.cloud.sqladmin_v1beta4.SqlDataServiceClient",
            return_value=mock_grpc_client,
        ),
        pytest.raises(
            ValueError,
            match="Cannot fallback to direct connection: no IP address available.",
        ),
    ):
        await client.connect(
            instance_connection_name="proj:region:inst",
            region="region",
            project="proj",
            get_conn_info=get_conn_info,
            enable_iam_auth=False,
            on_fallback=MagicMock(),
            is_fallback_cached=lambda _: False,
        )


@pytest.mark.asyncio
async def test_sqldata_client_direct_socket_factory_ip_retry_and_exhausted():
    creds = MagicMock(spec=Credentials)
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=creds,
    )

    mock_conn_info = MagicMock()
    mock_conn_info.get_preferred_ips.return_value = ["10.0.0.1", "10.0.0.2"]
    mock_ssl_ctx = MagicMock()
    mock_ssl_sock = MagicMock(spec=socket.socket)
    mock_ssl_ctx.wrap_socket.return_value = mock_ssl_sock
    mock_conn_info.create_ssl_context = AsyncMock(return_value=mock_ssl_ctx)
    get_conn_info = AsyncMock(return_value=mock_conn_info)

    mock_grpc_client = MagicMock()
    mock_grpc_client.transport.stream_sql_data = mock_grpc_client.stream_sql_data
    mock_grpc_client.stream_sql_data.side_effect = MockRpcError(grpc.StatusCode.UNAVAILABLE)

    # First IP fails, second IP succeeds
    with patch(
        "google.cloud.sqladmin_v1beta4.SqlDataServiceClient",
        return_value=mock_grpc_client,
    ), patch(
        "socket.create_connection", side_effect=[OSError("conn ref"), MagicMock()]
    ):
        sock = await client.connect(
            instance_connection_name="proj:region:inst",
            region="region",
            project="proj",
            get_conn_info=get_conn_info,
            enable_iam_auth=False,
            on_fallback=MagicMock(),
            is_fallback_cached=lambda _: False,
        )
        assert sock is mock_ssl_sock

    # All IPs fail
    with patch(
        "google.cloud.sqladmin_v1beta4.SqlDataServiceClient",
        return_value=mock_grpc_client,
    ), patch(
        "socket.create_connection", side_effect=OSError("all ips failed")
    ), pytest.raises(OSError, match="all ips failed"):
        await client.connect(
            instance_connection_name="proj:region:inst",
            region="region",
            project="proj",
            get_conn_info=get_conn_info,
            enable_iam_auth=False,
            on_fallback=MagicMock(),
            is_fallback_cached=lambda _: False,
        )


@pytest.mark.asyncio
async def test_sqldata_client_connect_resource_exhausted():
    creds = MagicMock(spec=Credentials)
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=creds,
    )

    on_res_exhausted = MagicMock()
    mock_conn_info = MagicMock()
    mock_conn_info.get_preferred_ips.return_value = ["10.0.0.1"]
    mock_conn_info.create_ssl_context = AsyncMock()
    get_conn_info = AsyncMock(return_value=mock_conn_info)

    rpc_err = MockRpcError(grpc.StatusCode.RESOURCE_EXHAUSTED)
    mock_grpc_client = MagicMock()
    mock_grpc_client.transport.stream_sql_data = mock_grpc_client.stream_sql_data
    mock_grpc_client.stream_sql_data.side_effect = rpc_err

    with patch(
        "google.cloud.sqladmin_v1beta4.SqlDataServiceClient",
        return_value=mock_grpc_client,
    ):
        with pytest.raises(MockRpcError):
            await client.connect(
                instance_connection_name="proj:region:inst",
                region="region",
                project="proj",
                get_conn_info=get_conn_info,
                enable_iam_auth=False,
                on_fallback=MagicMock(),
                is_fallback_cached=lambda _: False,
                on_resource_exhausted=on_res_exhausted,
            )

        on_res_exhausted.assert_called_once_with(rpc_err)


@pytest.mark.asyncio
async def test_sqldata_client_close_exceptions():
    creds = MagicMock(spec=Credentials)
    client = SqlDataClient(
        endpoint="sqladmin.googleapis.com",
        credentials=creds,
    )

    mock_sock = MagicMock(spec=SqlDataSocket)
    mock_sock.close.side_effect = RuntimeError("sock close error")
    client._active_sockets.add(mock_sock)

    broken_cb = MagicMock(side_effect=RuntimeError("cb error"))
    client._on_close_callbacks.append(broken_cb)

    # Should not raise exception
    await client.close()
    mock_sock.close.assert_called_once()
    broken_cb.assert_called_once()


def test_sqldata_socket_timeout():
    mock_response_stream = MagicMock()
    mock_grpc_client = MagicMock()
    mock_grpc_client.transport.stream_sql_data = mock_grpc_client.stream_sql_data
    req_queue = _RequestQueue()

    def stream_blocking():
        time.sleep(2.0)
        yield sqladmin_v1beta4.StreamSqlDataResponse()

    mock_response_stream.__iter__.side_effect = stream_blocking

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
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

    mock_grpc_client = MagicMock()
    mock_grpc_client.transport.stream_sql_data = mock_grpc_client.stream_sql_data
    mock_stream = MagicMock()

    def stream_gen():
        time.sleep(1.0)
        yield sqladmin_v1beta4.StreamSqlDataResponse()

    mock_stream.__iter__.side_effect = stream_gen
    mock_grpc_client.stream_sql_data.return_value = mock_stream

    with patch(
        "google.cloud.sqladmin_v1beta4.SqlDataServiceClient",
        return_value=mock_grpc_client,
    ):
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

    mock_grpc_client = MagicMock()
    mock_grpc_client.transport.stream_sql_data = mock_grpc_client.stream_sql_data
    rpc_err = MockRpcError(grpc.StatusCode.UNAVAILABLE)
    mock_grpc_client.stream_sql_data.side_effect = rpc_err

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

    with patch(
        "google.cloud.sqladmin_v1beta4.SqlDataServiceClient",
        return_value=mock_grpc_client,
    ), patch(
        "socket.create_connection", return_value=mock_raw_sock
    ):
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


def test_sqldata_socket_transparent_fallback():
    mock_response_stream = MagicMock()
    mock_grpc_client = MagicMock()
    req_queue = _RequestQueue()

    # Simulate gRPC stream raising FAILED_PRECONDITION on first read
    def stream_failing():
        time.sleep(0.05)
        raise MockRpcError(grpc.StatusCode.FAILED_PRECONDITION)
        yield  # Make it a generator

    mock_response_stream.__iter__.side_effect = stream_failing

    mock_direct_sock = MagicMock(spec=socket.socket)
    mock_direct_sock.recv.return_value = b"direct server response"
    fallback_called = False

    def fallback_fn():
        nonlocal fallback_called
        fallback_called = True
        return mock_direct_sock

    sock = SqlDataSocket(
        request_queue=req_queue,
        response_stream=mock_response_stream,
        grpc_client=mock_grpc_client,
        timeout=2.0,
        fallback_fn=fallback_fn,
    )

    # Client writes startup message before first read
    sock.sendall(b"startup message")

    # Client reads response -> triggers fallback, replays write, returns direct response
    resp = sock.recv(1024)

    assert fallback_called is True
    assert resp == b"direct server response"
    mock_direct_sock.sendall.assert_called_once_with(b"startup message")
    mock_direct_sock.recv.assert_called_once_with(1024, 0)
    sock.close()


