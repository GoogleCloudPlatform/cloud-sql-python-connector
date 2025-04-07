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
import os
from typing import Any, Union

import asyncpg
import sqlalchemy
import sqlalchemy.ext.asyncio

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import DefaultResolver
from google.cloud.sql.connector import DnsResolver


async def create_sqlalchemy_engine(
    instance_connection_name: str,
    user: str,
    password: str,
    db: str,
    ip_type: str = "public",
    refresh_strategy: str = "background",
    resolver: Union[type[DefaultResolver], type[DnsResolver]] = DefaultResolver,
    **kwargs: Any,
) -> tuple[sqlalchemy.ext.asyncio.engine.AsyncEngine, Connector]:
    """Creates a connection pool for a Cloud SQL instance and returns the pool
    and the connector. Callers are responsible for closing the pool and the
    connector.

    A sample invocation looks like:

        engine, connector = await create_sqlalchemy_engine(
            inst_conn_name,
            user,
            password,
            db,
        )
        async with engine.connect() as conn:
            time = (await conn.execute(sqlalchemy.text("SELECT NOW()"))).fetchone()
            curr_time = time[0]
            # do something with query result
            await connector.close_async()

    Args:
        instance_connection_name (str):
            The instance connection name specifies the instance relative to the
            project and region. For example: "my-project:my-region:my-instance"
        user (str):
            The database user name, e.g., postgres
        password (str):
            The database user's password, e.g., secret-password
        db (str):
            The name of the database, e.g., mydb
        ip_type (str):
            The IP type of the Cloud SQL instance to connect to. Can be one
            of "public", "private", or "psc".
        refresh_strategy (Optional[str]):
            Refresh strategy for the Cloud SQL Connector. Can be one of "lazy"
            or "background". For serverless environments use "lazy" to avoid
            errors resulting from CPU being throttled.
        resolver (Optional[google.cloud.sql.connector.DefaultResolver]):
            Resolver class for resolving instance connection name. Use
            google.cloud.sql.connector.DnsResolver when resolving DNS domain
            names or google.cloud.sql.connector.DefaultResolver for regular
            instance connection names ("my-project:my-region:my-instance").
    """
    loop = asyncio.get_running_loop()
    connector = Connector(
        loop=loop, refresh_strategy=refresh_strategy, resolver=resolver
    )

    # create SQLAlchemy connection pool
    engine = sqlalchemy.ext.asyncio.create_async_engine(
        "postgresql+asyncpg://",
        async_creator=lambda: connector.connect_async(
            instance_connection_name,
            "asyncpg",
            user=user,
            password=password,
            db=db,
            ip_type=ip_type,  # can be "public", "private" or "psc"
            **kwargs,  # additional asyncpg connection args
        ),
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    return engine, connector


async def create_asyncpg_pool(
    instance_connection_name: str,
    user: str,
    password: str,
    db: str,
    ip_type: str = "public",
    refresh_strategy: str = "background",
) -> tuple[asyncpg.Pool, Connector]:
    """Creates a native asyncpg connection pool for a Cloud SQL instance and
    returns the pool and the connector. Callers are responsible for closing the
    pool and the connector.

    A sample invocation looks like:

        pool, connector = await create_asyncpg_pool(
            inst_conn_name,
            user,
            password,
            db,
        )
        async with pool.acquire() as conn:
            hello = await conn.fetch("SELECT 'Hello World!'")
            # do something with query result
            await connector.close_async()

    Args:
        instance_connection_name (str):
            The instance connection name specifies the instance relative to the
            project and region. For example: "my-project:my-region:my-instance"
        user (str):
            The database user name, e.g., postgres
        password (str):
            The database user's password, e.g., secret-password
        db (str):
            The name of the database, e.g., mydb
        ip_type (str):
            The IP type of the Cloud SQL instance to connect to. Can be one
            of "public", "private", or "psc".
        refresh_strategy (Optional[str]):
            Refresh strategy for the Cloud SQL Connector. Can be one of "lazy"
            or "background". For serverless environments use "lazy" to avoid
            errors resulting from CPU being throttled.
    """
    loop = asyncio.get_running_loop()
    connector = Connector(loop=loop, refresh_strategy=refresh_strategy)

    async def getconn(
        instance_connection_name: str, **kwargs: Any
    ) -> asyncpg.Connection:
        conn: asyncpg.Connection = await connector.connect_async(
            instance_connection_name,
            "asyncpg",
            user=user,
            password=password,
            db=db,
            ip_type=ip_type,  # can be "public", "private" or "psc"
            **kwargs,
        )
        return conn

    # create native asyncpg pool (requires asyncpg version >=0.30.0)
    pool = await asyncpg.create_pool(instance_connection_name, connect=getconn)
    return pool, connector


async def test_sqlalchemy_connection_with_asyncpg() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    pool, connector = await create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type
    )

    async with pool.connect() as conn:
        res = (await conn.execute(sqlalchemy.text("SELECT 1"))).fetchone()
        assert res[0] == 1

    await connector.close_async()


async def test_lazy_sqlalchemy_connection_with_asyncpg() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    pool, connector = await create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type, "lazy"
    )

    async with pool.connect() as conn:
        res = (await conn.execute(sqlalchemy.text("SELECT 1"))).fetchone()
        assert res[0] == 1

    await connector.close_async()


async def test_custom_SAN_with_dns_sqlalchemy_connection_with_asyncpg() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CUSTOMER_CAS_PASS_VALID_DOMAIN_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_CUSTOMER_CAS_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    pool, connector = await create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type, resolver=DnsResolver
    )

    async with pool.connect() as conn:
        res = (await conn.execute(sqlalchemy.text("SELECT 1"))).fetchone()
        assert res[0] == 1

    await connector.close_async()


async def test_MCP_sqlalchemy_connection_with_asyncpg() -> None:
    """Basic test to get time from database using MCP enabled instance."""
    inst_conn_name = os.environ["POSTGRES_MCP_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_MCP_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    pool, connector = await create_sqlalchemy_engine(
        inst_conn_name,
        user,
        password,
        db,
        ip_type,
        statement_cache_size=0,
    )

    async with pool.connect() as conn:
        res = (await conn.execute(sqlalchemy.text("SELECT 1"))).fetchone()
        assert res[0] == 1

    await connector.close_async()


async def test_connection_with_asyncpg() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    pool, connector = await create_asyncpg_pool(
        inst_conn_name, user, password, db, ip_type
    )

    async with pool.acquire() as conn:
        res = await conn.fetch("SELECT 1")
        assert res[0][0] == 1

    await connector.close_async()


async def test_lazy_connection_with_asyncpg() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    pool, connector = await create_asyncpg_pool(
        inst_conn_name, user, password, db, ip_type, "lazy"
    )

    async with pool.acquire() as conn:
        res = await conn.fetch("SELECT 1")
        assert res[0][0] == 1

    await connector.close_async()
