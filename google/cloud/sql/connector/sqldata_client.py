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

import errno
import io
import logging
import queue
import socket
import threading
from typing import Any, Callable

from google.auth.credentials import Credentials
from google.auth.transport.grpc import AuthMetadataPlugin
from google.auth.transport.requests import Request
import grpc

from google.cloud.sql.connector.enums import IPTypes
from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError
from google.cloud.sql.connector.proto import sql_data_service_pb2  # type: ignore
from google.cloud.sql.connector.proto import sql_data_service_pb2_grpc  # type: ignore

SERVER_PROXY_PORT = 3307
_EOF_SENTINEL = object()
_STREAM_EOF = object()

logger = logging.getLogger(__name__)


def is_resource_exhausted_error(err: Exception) -> bool:
    """Checks whether an exception represents a gRPC RESOURCE_EXHAUSTED error."""
    if isinstance(err, grpc.RpcError):
        try:
            return err.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
        except Exception:  # noqa: BLE001, S110
            pass
    if hasattr(err, "code") and callable(err.code):
        try:
            return err.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
        except Exception:  # noqa: BLE001, S110
            pass
    cause = getattr(err, "__cause__", None) or getattr(err, "__context__", None)
    if isinstance(cause, Exception) and cause is not err:
        return is_resource_exhausted_error(cause)
    return False


class _RequestQueue:
    """Thread-safe queue iterator feeding requests to synchronous gRPC stream."""

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=1024)
        self._closed = False
        self._lock = threading.Lock()

    def put(self, item: Any) -> None:
        with self._lock:
            if self._closed:
                raise BrokenPipeError(errno.EPIPE, "Stream request queue is closed")
            self._queue.put(item)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._queue.put(_STREAM_EOF)

    def __iter__(self) -> _RequestQueue:
        return self

    def __next__(self) -> Any:
        item = self._queue.get()
        if item is _STREAM_EOF:
            raise StopIteration
        return item


class SqlDataRawIO(io.RawIOBase):
    """RawIO wrapper around SqlDataSocket to support makefile()."""

    def __init__(self, sock: SqlDataSocket) -> None:
        self._sock = sock

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def readinto(self, b: Any) -> int:
        return self._sock.recv_into(b)

    def write(self, b: Any) -> int:
        self._sock.sendall(b)
        return len(b)

    def close(self) -> None:
        if not self.closed:
            super().close()
            self._sock.close()


class SqlDataSocket(socket.socket):
    """Direct in-process socket adapter connected to a synchronous gRPC SqlData stream.

    Provides full socket interface compatibility for synchronous database drivers
    (pg8000, pymysql, pytds) while avoiding local TCP loopback and asyncio scheduling.
    """

    def __init__(
        self,
        request_queue: _RequestQueue,
        response_stream: Any,
        channel: grpc.Channel,
        timeout: float | None = None,
        on_close: Callable[[], None] | None = None,
        on_success: Callable[[], None] | None = None,
        on_resource_exhausted: Callable[[Exception], None] | None = None,
    ) -> None:
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self._request_queue = request_queue
        self._response_stream = response_stream
        self._channel = channel
        self._timeout = timeout
        self._on_close = on_close
        self._on_success = on_success
        self._on_resource_exhausted = on_resource_exhausted

        self._read_queue: queue.Queue = queue.Queue(maxsize=1024)
        self._read_buf = b""
        self._read_offset = 0
        self._closed = False
        self._first_read_done = False
        self._error: Exception | None = None
        self._close_lock = threading.Lock()

        # Telemetry / Profiling counters

        # Start background stream consumer thread
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="sqldata-reader"
        )
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        try:
            for resp in self._response_stream:
                if self._closed:
                    break
                if not self._first_read_done:
                    self._first_read_done = True
                    if self._on_success:
                        self._on_success()
                msg_type = resp.WhichOneof("message")
                if msg_type == "data":
                    data = resp.data.data
                    if data:
                        self._read_queue.put(data)
                elif msg_type == "session_metadata":
                    logger.debug("Received SessionMetadata")
                elif msg_type == "terminate_session":
                    logger.debug("Received TerminateSession from server")
                    self._closed = True
                    break
        except Exception as e:  # noqa: BLE001
            if not self._closed:
                logger.debug(f"gRPC sync stream reader encountered: {e}")
                self._error = e
                if is_resource_exhausted_error(e) and self._on_resource_exhausted:
                    self._on_resource_exhausted(e)
        finally:
            self._read_queue.put(_EOF_SENTINEL)

    def sendall(  # type: ignore[override]
        self, data: Any, flags: int = 0
    ) -> None:
        if self._closed:
            raise BrokenPipeError(errno.EPIPE, "Socket is closed")
        if not data:
            return
        data_bytes = bytes(data) if not isinstance(data, bytes) else data
        packet = sql_data_service_pb2.DataPacket(data=data_bytes)  # type: ignore[attr-defined]
        req = sql_data_service_pb2.StreamSqlDataRequest(data=packet)  # type: ignore[attr-defined]
        self._request_queue.put(req)

    def send(  # type: ignore[override]
        self, data: Any, flags: int = 0
    ) -> int:
        self.sendall(data, flags)
        return len(data)

    def recv(self, bufsize: int, flags: int = 0) -> bytes:
        if bufsize <= 0:
            return b""

        # Return from buffered chunk if available
        if self._read_offset < len(self._read_buf):
            remaining = len(self._read_buf) - self._read_offset
            to_copy = min(bufsize, remaining)
            chunk = self._read_buf[self._read_offset : self._read_offset + to_copy]
            self._read_offset += to_copy
            if self._read_offset >= len(self._read_buf):
                self._read_buf = b""
                self._read_offset = 0
            return chunk

        # Pull from incoming queue
        try:
            item = self._read_queue.get(block=True, timeout=self._timeout)
        except queue.Empty:
            if self._closed:
                return b""
            raise socket.timeout("timed out")

        if item is _EOF_SENTINEL:
            if self._error is not None:
                raise OSError(
                    errno.ECONNRESET, f"Connection error: {self._error}"
                ) from self._error
            return b""

        if len(item) <= bufsize:
            return item

        self._read_buf = item
        self._read_offset = bufsize
        return item[:bufsize]

    def recv_into(self, buffer: Any, nbytes: int = 0, flags: int = 0) -> int:
        target_len = len(buffer) if nbytes == 0 else min(nbytes, len(buffer))
        if target_len <= 0:
            return 0
        data = self.recv(target_len, flags)
        n = len(data)
        buffer[:n] = data
        return n

    def makefile(  # type: ignore[override]
        self,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> Any:
        raw = SqlDataRawIO(self)
        if buffering == 0:
            return raw

        reading = "r" in mode or "+" in mode
        writing = "w" in mode or "a" in mode or "+" in mode
        binary = "b" in mode

        buf: Any
        if reading and writing:
            buf = io.BufferedRWPair(raw, raw)
        elif reading:
            buffer_size = io.DEFAULT_BUFFER_SIZE if buffering <= 0 else buffering
            buf = io.BufferedReader(raw, buffer_size=buffer_size)
        elif writing:
            buffer_size = io.DEFAULT_BUFFER_SIZE if buffering <= 0 else buffering
            buf = io.BufferedWriter(raw, buffer_size=buffer_size)
        else:
            buffer_size = io.DEFAULT_BUFFER_SIZE if buffering <= 0 else buffering
            buf = io.BufferedReader(raw, buffer_size=buffer_size)

        if binary:
            return buf
        return io.TextIOWrapper(
            buf, encoding=encoding, errors=errors, newline=newline
        )

    def settimeout(self, value: float | None) -> None:
        if value is not None and value < 0:
            raise ValueError("Timeout value must be non-negative")
        self._timeout = value

    def gettimeout(self) -> float | None:
        return self._timeout

    def setblocking(self, flag: bool) -> None:
        self._timeout = None if flag else 0.0

    def connect(self, *args: Any, **kwargs: Any) -> None:
        # Already connected, no-op for driver compatibility (e.g. pymysql)
        pass

    def connect_ex(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def setsockopt(self, *args: Any, **kwargs: Any) -> None:
        # Gracefully accept socket options (e.g., TCP_NODELAY, SO_KEEPALIVE)
        pass

    def getsockopt(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        return 0

    def getsockname(self) -> tuple[str, int]:
        return ("127.0.0.1", SERVER_PROXY_PORT)

    def getpeername(self) -> tuple[str, int]:
        return ("127.0.0.1", SERVER_PROXY_PORT)

    def shutdown(self, how: int = socket.SHUT_RDWR) -> None:
        self.close()

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True


        self._request_queue.close()
        self._read_queue.put(_EOF_SENTINEL)
        try:
            if hasattr(self._response_stream, "cancel"):
                self._response_stream.cancel()
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            self._channel.close()
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            super().close()
        except Exception:  # noqa: BLE001, S110
            pass

        if self._on_close:
            try:
                self._on_close()
            except Exception:  # noqa: BLE001, S110
                pass


class SqlDataClient:
    """Client that establishes direct synchronous gRPC SqlDataService connections."""

    def __init__(
        self,
        endpoint: str,
        credentials: Credentials,
        quota_project: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._credentials = credentials
        self._quota_project = quota_project
        self._timeout = timeout
        self._active_sockets: set[SqlDataSocket] = set()
        self._on_close_callbacks: list[Callable[[], None]] = []

    async def connect(
        self,
        instance_connection_name: str,
        region: str,
        project: str,
        get_conn_info: Callable[[], Any],
        enable_iam_auth: bool,
        on_fallback: Callable[[str], None],
        is_fallback_cached: Callable[[str], bool],
        on_resource_exhausted: Callable[[Exception], None] | None = None,
        on_success: Callable[[], None] | None = None,
        connect_timeout: float = 30.0,
    ) -> socket.socket:
        """Connects via synchronous gRPC and returns a SqlDataSocket or direct TLS fallback socket."""
        use_fallback = is_fallback_cached(instance_connection_name)

        async def connect_direct() -> socket.socket:
            logger.debug("Fallback triggered, fetching connection info...")
            conn_info = await get_conn_info()
            targets: list[str] = []
            for t in [IPTypes.PRIVATE, IPTypes.PSC, IPTypes.PUBLIC]:
                try:
                    targets.extend(conn_info.get_preferred_ips(t))
                except CloudSQLIPTypeError as e:
                    logger.debug(f"IP type {t} not available: {e}")
                    continue
            if not targets:
                raise ValueError(
                    "Cannot fallback to direct connection: no IP address available."
                )
            ssl_context = await conn_info.create_ssl_context(enable_iam_auth)
            last_ex: Exception | None = None
            for target_ip in targets:
                logger.debug(f"Direct TLS connecting to {target_ip}:{SERVER_PROXY_PORT}")
                try:
                    raw_sock = socket.create_connection(
                        (target_ip, SERVER_PROXY_PORT), timeout=connect_timeout
                    )
                    ssl_sock = ssl_context.wrap_socket(
                        raw_sock, server_hostname=target_ip
                    )
                    return ssl_sock
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"Direct TLS connection to {target_ip} failed: {e}")
                    last_ex = e
            if last_ex:
                raise last_ex
            raise ValueError(
                "Cannot fallback to direct connection: no IP address available."
            )

        if use_fallback:
            logger.debug("Using cached fallback direct TLS connection")
            return await connect_direct()

        # Connect synchronous gRPC stream
        auth_request = Request()
        plugin = AuthMetadataPlugin(self._credentials, auth_request)
        call_creds = grpc.metadata_call_credentials(plugin)
        channel_creds = grpc.composite_channel_credentials(
            grpc.ssl_channel_credentials(), call_creds
        )

        endpoint = self._endpoint.removeprefix("https://").removeprefix("http://")
        channel = grpc.secure_channel(endpoint, channel_creds)

        instance_id = (
            f"projects/{project}/instances/{instance_connection_name.split(':')[-1]}"
        )
        location_id = f"locations/{region}"

        metadata = []
        quota_project_in_creds = getattr(self._credentials, "quota_project_id", None)
        if self._quota_project and self._quota_project != quota_project_in_creds:
            metadata.append(("x-goog-user-project", self._quota_project))
        metadata.append(
            (
                "x-goog-request-params",
                f"instance_id={instance_id}&location_id={location_id}",
            )
        )

        stub = sql_data_service_pb2_grpc.SqlDataServiceStub(channel)

        try:
            request_queue = _RequestQueue()
            start_session = sql_data_service_pb2.StartSession(  # type: ignore[attr-defined]
                instance_id=instance_id, location_id=location_id
            )
            req = sql_data_service_pb2.StreamSqlDataRequest(  # type: ignore[attr-defined]
                start_session=start_session
            )
            request_queue.put(req)

            response_stream = stub.StreamSqlData(
                request_queue, metadata=metadata, timeout=self._timeout
            )

            sock = SqlDataSocket(
                request_queue=request_queue,
                response_stream=response_stream,
                channel=channel,
                timeout=connect_timeout,
                on_close=lambda: self._active_sockets.discard(sock),
                on_success=on_success,
                on_resource_exhausted=on_resource_exhausted,
            )
            self._active_sockets.add(sock)
            return sock

        except Exception as e:
            logger.debug(f"Sync gRPC connection attempt failed: {e}")
            try:
                channel.close()
            except Exception:  # noqa: BLE001, S110
                pass

            if is_resource_exhausted_error(e):
                if on_resource_exhausted:
                    on_resource_exhausted(e)
                raise

            # Fallback to direct TLS on connection failure
            logger.info(
                f"SQL Data Service connection failed for {instance_connection_name}. "
                "Falling back to direct TLS connection."
            )
            on_fallback(instance_connection_name)
            return await connect_direct()

    async def close(self) -> None:
        """Closes all active sockets created by this client."""
        for sock in list(self._active_sockets):
            try:
                sock.close()
            except Exception:  # noqa: BLE001, S110
                pass
        self._active_sockets.clear()
        for cb in self._on_close_callbacks:
            try:
                cb()
            except Exception:  # noqa: BLE001, S110
                pass
