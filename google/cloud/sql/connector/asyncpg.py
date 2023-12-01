"""
Copyright 2022 Google LLC

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
import asyncio
import contextvars
import functools
import socket
import ssl
from typing import Any, TYPE_CHECKING

SERVER_PROXY_PORT = 3307

if TYPE_CHECKING:
    import asyncpg


def sock_func(ip_address: str) -> socket.socket:
    return socket.create_connection((ip_address, SERVER_PROXY_PORT))


async def connect(
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
) -> "asyncpg.Connection":
    """Helper function to create an asyncpg DB-API connection object.

    :type ip_address: str
    :param ip_address: A string containing an IP address for the Cloud SQL
        instance.

    :type ctx: ssl.SSLContext
    :param ctx: An SSLContext object created from the Cloud SQL server CA
        cert and ephemeral cert.

    :type kwargs: Any
    :param kwargs: Keyword arguments for establishing asyncpg connection
        object to Cloud SQL instance.

    :rtype: asyncpg.Connection
    :returns: An asyncpg.Connection object to a Cloud SQL instance.
    """
    try:
        import asyncpg
    except ImportError:
        raise ImportError(
            'Unable to import module "asyncpg." Please install and try again.'
        )

    async def async_sock_func() -> socket.socket:
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        func_call = functools.partial(ctx.run, sock_func, ip_address)
        return await loop.run_in_executor(None, func_call)

    user = kwargs.pop("user")
    db = kwargs.pop("db")
    passwd = kwargs.pop("password", None)

    return await asyncpg.connect(
        user=user,
        database=db,
        password=passwd,
        ssl=ctx,
        socket_callback=async_sock_func,
        **kwargs,
    )
