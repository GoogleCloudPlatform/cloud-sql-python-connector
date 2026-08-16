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

import asyncio
import logging
import socket
from typing import Any, Callable

from google.auth.credentials import Credentials
from google.auth.transport.grpc import AuthMetadataPlugin
from google.auth.transport.requests import Request
import grpc

from google.cloud.sql.connector.exceptions import CloudSQLIPTypeError

import google.rpc.status_pb2  # noqa: F401 # isort: skip
from google.cloud.sql.connector.proto import sql_data_service_pb2  # type: ignore
from google.cloud.sql.connector.proto import sql_data_service_pb2_grpc  # type: ignore

logger = logging.getLogger(__name__)


class SqlDataClient:
    def __init__(
        self,
        endpoint: str,
        credentials: Credentials,
        quota_project: str | None = None,
        timeout: float | None = None,
    ):
        self._endpoint = endpoint
        self._credentials = credentials
        self._quota_project = quota_project
        self._timeout = timeout
        self._server: asyncio.Server | None = None
        self._tunnel_tasks: set[asyncio.Task] = set()
        self._active_grpc_channels: set[grpc.aio.Channel] = set()
        self._active_writers: set[asyncio.StreamWriter] = set()
        self._on_close_callbacks: list[Callable[[], None]] = []

    async def connect_tunnel(
        self,
        instance_connection_name: str,
        region: str,
        project: str,
        get_conn_info: Callable[[], Any],
        enable_iam_auth: bool,
        on_fallback: Callable[[str], None],
        is_fallback_cached: Callable[[str], bool],
    ) -> int:
        """Starts a local TCP tunnel and returns the local port.

        If the instance does not support SQL Data Service, it falls back
        to a direct TLS connection.
        """
        # Start local TCP server
        server = await asyncio.start_server(
            lambda r, w: self._handle_tunnel(
                r,
                w,
                instance_connection_name,
                region,
                project,
                get_conn_info,
                enable_iam_auth,
                on_fallback,
                is_fallback_cached,
            ),
            "127.0.0.1",
            0,
        )

        port = server.sockets[0].getsockname()[1]
        logger.debug(f"SQL Data tunnel listening on 127.0.0.1:{port}")

        # Keep reference to server to close it
        self._server = server
        return port

    async def close(self) -> None:
        """Closes the local tunnel server, active streams, and channels."""
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=2.0)
                logger.debug("SQL Data tunnel server closed by client close()")
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for SQL Data tunnel server to close")
            self._server = None

        for task in list(self._tunnel_tasks):
            task.cancel()

        for channel in list(self._active_grpc_channels):
            try:
                await channel.close()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Error closing gRPC channel: {e}")
        self._active_grpc_channels.clear()

        for writer in list(self._active_writers):
            try:
                writer.close()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Error closing stream writer: {e}")
        self._active_writers.clear()

        for cb in self._on_close_callbacks:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    async def _handle_tunnel(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        instance_connection_name: str,
        region: str,
        project: str,
        get_conn_info: Callable[[], Any],
        enable_iam_auth: bool,
        on_fallback: Callable[[str], None],
        is_fallback_cached: Callable[[str], bool],
    ):
        logger.debug("Accepted local connection for SQL Data tunnel")
        # Close the server so no more connections are accepted on this port
        self._server.close()
        self._active_writers.add(client_writer)

        # Buffer to cache client writes for fallback replay
        client_write_buffer = bytearray()
        first_read_done = False
        fallback_triggered = False

        # We need to share these streams between tasks
        backend_reader: asyncio.StreamReader | None = None
        backend_writer: asyncio.StreamWriter | None = None
        grpc_stream: Any | None = None
        grpc_channel: grpc.aio.Channel | None = None

        # Check if fallback is already cached
        use_fallback = is_fallback_cached(instance_connection_name)

        async def connect_grpc() -> tuple[grpc.aio.Channel, Any]:
            auth_request = Request()
            plugin = AuthMetadataPlugin(self._credentials, auth_request)
            call_creds = grpc.metadata_call_credentials(plugin)
            channel_creds = grpc.composite_channel_credentials(
                grpc.ssl_channel_credentials(), call_creds
            )

            endpoint = self._endpoint.removeprefix("https://").removeprefix("http://")

            logger.debug(f"Creating secure channel to {endpoint}")
            channel = grpc.aio.secure_channel(endpoint, channel_creds)
            self._active_grpc_channels.add(channel)
            stub = sql_data_service_pb2_grpc.SqlDataServiceStub(channel)

            instance_id = f"projects/{project}/instances/{instance_connection_name.split(':')[-1]}"
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

            # Start stream
            logger.debug(f"Starting StreamSqlData with metadata {metadata}")
            stream = stub.StreamSqlData(metadata=metadata, timeout=self._timeout)

            # Send StartSession
            start_session = sql_data_service_pb2.StartSession(  # type: ignore[attr-defined]
                instance_id=instance_id, location_id=location_id
            )
            req = sql_data_service_pb2.StreamSqlDataRequest(  # type: ignore[attr-defined]
                start_session=start_session
            )
            logger.debug("Writing StartSession to stream...")
            await stream.write(req)
            logger.debug("StartSession written successfully")
            return channel, stream

        async def connect_direct() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
            logger.debug("Fallback triggered, fetching connection info...")
            conn_info = await get_conn_info()
            # Find a fallback IP address
            targets: list[str] = []
            from google.cloud.sql.connector.enums import IPTypes
            for t in [IPTypes.PRIVATE, IPTypes.PUBLIC, IPTypes.PSC]:
                try:
                    targets.extend(conn_info.get_preferred_ips(t))
                except CloudSQLIPTypeError as e:
                    logger.debug(f"IP type {t} not available: {e}")
                    continue
            if not targets:
                raise ValueError("Cannot fallback to direct connection: no IP address available.")
            ssl_context = await conn_info.create_ssl_context(enable_iam_auth)
            last_ex: Exception | None = None
            for target_ip in targets:
                logger.debug(f"Connecting directly to {target_ip}:3307")
                try:
                    r, w = await asyncio.open_connection(
                        target_ip, 3307, ssl=ssl_context, server_hostname=target_ip
                    )
                    self._active_writers.add(w)
                    return r, w
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"Direct connection to {target_ip} failed: {e}")
                    last_ex = e
            if last_ex:
                raise last_ex
            raise ValueError("Cannot fallback to direct connection: no IP address available.")

        fallback_ready = asyncio.Event()

        # Initialize connection
        if use_fallback:
            logger.debug("Using cached fallback connection")
            backend_reader, backend_writer = await connect_direct()
            fallback_triggered = True
            fallback_ready.set()
        else:
            try:
                grpc_channel, grpc_stream = await connect_grpc()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Failed to initialize gRPC stream: {e}")
                # Try fallback immediately
                backend_reader, backend_writer = await connect_direct()
                fallback_triggered = True
                fallback_ready.set()
                on_fallback(instance_connection_name)

        # Task to read from client and write to backend
        async def client_to_backend():
            nonlocal first_read_done, fallback_triggered, backend_writer, grpc_stream
            try:
                while True:
                    data = await client_reader.read(4096)
                    if not data:
                        logger.debug("Client socket EOF")
                        break

                    if not first_read_done and not fallback_triggered:
                        client_write_buffer.extend(data)

                    if fallback_triggered:
                        await fallback_ready.wait()
                        if backend_writer:
                            backend_writer.write(data)
                            await backend_writer.drain()
                    else:
                        packet = sql_data_service_pb2.DataPacket(data=data)  # type: ignore[attr-defined]
                        req = sql_data_service_pb2.StreamSqlDataRequest(  # type: ignore[attr-defined]
                            data=packet
                        )
                        if grpc_stream:
                            try:
                                await grpc_stream.write(req)
                            except Exception as e:
                                if fallback_triggered or not first_read_done:
                                    logger.debug(
                                        f"Write to gRPC stream failed while fallback pending or triggered: {e}"
                                    )
                                else:
                                    raise
            except Exception as e:
                logger.error(f"Error in client_to_backend: {e}")
                raise
            finally:
                if fallback_triggered:
                    if backend_writer:
                        backend_writer.write_eof()
                else:
                    if grpc_stream:
                        try:
                            await grpc_stream.done_writing()
                        except Exception as e:  # noqa: BLE001
                            logger.debug(f"Error calling done_writing: {e}")
                logger.debug("Client to backend task finished")

        # Task to read from backend and write to client
        async def backend_to_client():
            nonlocal first_read_done, fallback_triggered, backend_reader, backend_writer, grpc_stream, grpc_channel
            try:
                if fallback_triggered:
                    # If we started with fallback, just copy
                    while True:
                        if not backend_reader:
                            break
                        data = await backend_reader.read(4096)
                        if not data:
                            break
                        client_writer.write(data)
                        await client_writer.drain()
                else:
                    # gRPC read loop
                    try:
                        if not grpc_stream:
                            return
                        async for resp in grpc_stream:
                            first_read_done = True
                            msg_type = resp.WhichOneof("message")
                            if msg_type == "session_metadata":
                                logger.debug("Received SessionMetadata")
                            elif msg_type == "data":
                                data = resp.data.data
                                logger.debug(f"Received {len(data)} bytes")
                                client_writer.write(data)
                                await client_writer.drain()
                            elif msg_type == "terminate_session":
                                logger.debug("Received TerminateSession")
                                break
                    except grpc.aio.AioRpcError as e:
                        logger.debug(f"gRPC stream error: {e}")
                        # Check for fallback condition
                        if (
                            not first_read_done
                            and e.code() == grpc.StatusCode.FAILED_PRECONDITION
                        ):
                            logger.info(
                                f"SQL Data Service not supported for {instance_connection_name}. "
                                "Falling back to direct connection."
                            )
                            fallback_triggered = True
                            on_fallback(instance_connection_name)
                            
                            # Clean up gRPC
                            if grpc_channel:
                                await grpc_channel.close()
                            
                            # Connect direct
                            backend_reader, backend_writer = await connect_direct()
                            
                            # Replay buffered client data
                            if client_write_buffer:
                                logger.debug(f"Replaying {len(client_write_buffer)} bytes to fallback connection")
                                backend_writer.write(bytes(client_write_buffer))
                                await backend_writer.drain()
                            
                            fallback_ready.set()
                            
                            # Start copying from direct connection
                            while True:
                                data = await backend_reader.read(4096)
                                if not data:
                                    break
                                client_writer.write(data)
                                await client_writer.drain()
                        else:
                            # Other gRPC error, re-raise to close connection
                            raise
            except Exception as e:
                logger.error(f"Error in backend_to_client: {e}")
                raise
            finally:
                client_writer.close()
                try:
                    await client_writer.wait_closed()
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"Error waiting for client writer to close: {e}")
                if fallback_triggered and backend_writer:
                    backend_writer.close()
                    try:
                        await backend_writer.wait_closed()
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"Error waiting for backend writer to close: {e}")
                elif grpc_channel:
                    await grpc_channel.close()
                logger.debug("Backend to client task finished")

        # Run both tasks with explicit lifecycle and cancellation management
        t_client = asyncio.create_task(client_to_backend())
        t_backend = asyncio.create_task(backend_to_client())
        self._tunnel_tasks.add(t_client)
        self._tunnel_tasks.add(t_backend)
        try:
            done, pending = await asyncio.wait(
                [t_client, t_backend],
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            for task in done:
                if not task.cancelled() and task.exception() is not None:
                    raise task.exception()
        finally:
            self._tunnel_tasks.discard(t_client)
            self._tunnel_tasks.discard(t_backend)
            if grpc_channel:
                self._active_grpc_channels.discard(grpc_channel)
                try:
                    await grpc_channel.close()
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"Error closing gRPC channel: {e}")
            self._active_writers.discard(client_writer)
            if backend_writer:
                self._active_writers.discard(backend_writer)
            logger.debug("Closing client socket in _handle_tunnel finally")
            try:
                client_writer.close()
                sock = client_writer.get_extra_info("socket")
                if sock:
                    sock.close()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Error closing client writer: {e}")
            for cb in self._on_close_callbacks:
                try:
                    cb()
                except Exception:  # noqa: BLE001
                    pass
            logger.debug("SQL Data tunnel handler finished")


class FallbackSocket(socket.socket):
    def connect(self, *args: Any, **kwargs: Any) -> None:
        # Already connected, do nothing.
        # This is needed because some drivers (like pymysql) try to call connect()
        # internally even if passed an already connected socket.
        pass
