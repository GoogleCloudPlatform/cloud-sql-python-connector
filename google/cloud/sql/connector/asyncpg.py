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
import ssl
from typing import Any, Union, TYPE_CHECKING

SERVER_PROXY_PORT = 3307

if TYPE_CHECKING:
    import asyncpg


async def connect(
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
) -> "Union[asyncpg.Connection, asyncpg.Pool]":
    """Helper function to create an asyncpg DB-API connection object.

    :type ip_address: str
    :param ip_address: A string containing an IP address for the Cloud SQL
        instance.

    :type ctx: ssl.SSLContext
    :param ctx: An SSLContext object created from the Cloud SQL server CA
        cert and ephemeral cert.

    :type kwargs: Any
    :param kwargs: Keyword arguments for establishing connection object
        or connection pool to Cloud SQL instance.

    :rtype: Union[asyncpg.Connection, asyncpg.Pool]
    :returns: An asyncpg Connection or Pool object for the Cloud SQL instance.
    """
    try:
        import asyncpg
    except ImportError:
        raise ImportError(
            'Unable to import module "asyncpg." Please install and try again.'
        )
    user = kwargs.pop("user")
    db = kwargs.pop("db")
    passwd = kwargs.pop("password", None)
    pool = kwargs.pop("pool", False)
    # return connection pool if pool is set to True
    if pool:
        return await asyncpg.create_pool(
            user=user,
            database=db,
            password=passwd,
            host=ip_address,
            port=SERVER_PROXY_PORT,
            ssl=ctx,
            direct_tls=True,
            **kwargs,
        )
    # return regular asyncpg connection
    return await asyncpg.connect(
        user=user,
        database=db,
        password=passwd,
        host=ip_address,
        port=SERVER_PROXY_PORT,
        ssl=ctx,
        direct_tls=True,
        **kwargs,
    )
