""""
Copyright 2021 Google LLC

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
import os
import uuid
from typing import AsyncGenerator

import asyncpg
import pytest
from google.cloud.sql.connector import Connector

table_name = f"books_{uuid.uuid4().hex}"


@pytest.fixture(name="conn")
async def setup() -> AsyncGenerator:
    # initialize Cloud SQL Python Connector object
    connector = Connector()
    conn: asyncpg.Connection = await connector.connect_async(
        os.environ["POSTGRES_CONNECTION_NAME"],
        "asyncpg",
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASS"],
        db=os.environ["POSTGRES_DB"],
    )
    await conn.execute(
        f"CREATE TABLE IF NOT EXISTS {table_name}"
        " ( id CHAR(20) NOT NULL, title TEXT NOT NULL );"
    )

    yield conn

    await conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    # close asyncpg connection
    await conn.close()
    # cleanup Connector object
    connector.close()


@pytest.mark.asyncio
async def test__connection_with_asyncpg(conn: asyncpg.Connection) -> None:
    await conn.execute(
        f"INSERT INTO {table_name} (id, title) VALUES ('book1', 'Book One')"
    )
    await conn.execute(
        f"INSERT INTO {table_name} (id, title) VALUES ('book2', 'Book Two')"
    )

    rows = await conn.fetch(f"SELECT title FROM {table_name} ORDER BY ID")
    titles = [row[0] for row in rows]

    assert titles == ["Book One", "Book Two"]
