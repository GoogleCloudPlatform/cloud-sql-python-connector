"""
Copyright 2025 Google LLC

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
import os
import threading
from pathlib import Path

SERVER_PROXY_PORT = 3307

def start_local_proxy(
  ssl_sock,
  socket_path,
):
  path_parts = socket_path.rsplit('/', 1)
  parent_directory = '/'.join(path_parts[:-1])

  desired_path = Path(parent_directory)
  desired_path.mkdir(parents=True, exist_ok=True)

  if os.path.exists(socket_path):
      os.remove(socket_path)
  conn_unix = None
  unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

  unix_socket.bind(socket_path)
  unix_socket.listen(1)

  threading.Thread(target=local_communication, args=(unix_socket, ssl_sock, socket_path)).start()


def local_communication(
  unix_socket, ssl_sock, socket_path
):
  try:
    conn_unix, addr_unix = unix_socket.accept()

    while True:
      data = conn_unix.recv(10485760)
      if not data:
        break
      ssl_sock.sendall(data)
      response = ssl_sock.recv(10485760)
      conn_unix.sendall(response)

  finally:
    if conn_unix is not None:
      conn_unix.close()
    unix_socket.close()
    os.remove(socket_path) # Clean up the socket file
