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
from typing import AsyncGenerator
import uuid

import asyncpg
import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine

from google.cloud.sql.connector import Connector

table_name = f"books_{uuid.uuid4().hex}"


# The Cloud SQL Python Connector can be used along with SQLAlchemy using the
# 'async_creator' argument to 'create_async_engine'
async def init_connection_pool() -> AsyncEngine:
    async def getconn() -> asyncpg.Connection:
        loop = asyncio.get_running_loop()
        # initialize Connector object for connections to Cloud SQL
        async with Connector(loop=loop) as connector:
            conn: asyncpg.Connection = await connector.connect_async(
                os.environ["POSTGRES_IAM_CONNECTION_NAME"],
                "asyncpg",
                user=os.environ["POSTGRES_IAM_USER"],
                db=os.environ["POSTGRES_DB"],
                enable_iam_auth=True,
            )
            return conn

    # create SQLAlchemy connection pool
    pool = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=getconn,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    return pool


@pytest.fixture(name="pool")
async def setup() -> AsyncGenerator:
    pool = await init_connection_pool()
    async with pool.connect() as conn:
        await conn.execute(
            sqlalchemy.text(
                f"CREATE TABLE IF NOT EXISTS {table_name}"
                " ( id CHAR(20) NOT NULL, title TEXT NOT NULL );"
            )
        )

    yield pool

    async with pool.connect() as conn:
        await conn.execute(sqlalchemy.text(f"DROP TABLE IF EXISTS {table_name}"))
    # dispose of asyncpg connection pool
    await pool.dispose()


@pytest.mark.asyncio
async def test_connection_with_asyncpg_iam_auth(pool: AsyncEngine) -> None:
    insert_stmt = sqlalchemy.text(
        f"INSERT INTO {table_name} (id, title) VALUES (:id, :title)",
    )
    async with pool.connect() as conn:
        await conn.execute(insert_stmt, parameters={"id": "book1", "title": "Book One"})
        await conn.execute(insert_stmt, parameters={"id": "book2", "title": "Book Two"})

        select_stmt = sqlalchemy.text(f"SELECT title FROM {table_name} ORDER BY ID;")
        rows = (await conn.execute(select_stmt)).fetchall()
        titles = [row[0] for row in rows]

    assert titles == ["Book One", "Book Two"]
