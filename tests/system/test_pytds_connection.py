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
from typing import Generator

import pytds
import pytest
import sqlalchemy
from google.cloud.sql.connector import connector

table_name = f"books_{uuid.uuid4().hex}"


# [START cloud_sql_connector_mysql_pytds]
# The Cloud SQL Python Connector can be used along with SQLAlchemy using the
# 'creator' argument to 'create_engine'. To use SQLAlchemy with pytds, include
# 'sqlalchemy-pytds` in your dependencies
def init_connection_engine() -> sqlalchemy.engine.Engine:
    def getconn() -> pytds.Connection:
        conn = connector.connect(
            os.environ["SQLSERVER_CONNECTION_NAME"],
            "pytds",
            user=os.environ["SQLSERVER_USER"],
            password=os.environ["SQLSERVER_PASS"],
            db=os.environ["SQLSERVER_DB"],
        )
        return conn

    engine = sqlalchemy.create_engine(
        "mssql+pytds://localhost",
        creator=getconn,
    )
    engine.dialect.description_encoding = None
    return engine


# [END cloud_sql_connector_mysql_pytds]


@pytest.fixture(name="pool")
def setup() -> Generator:
    pool = init_connection_engine()

    with pool.connect() as conn:
        conn.execute(
            f"CREATE TABLE {table_name}"
            " ( id CHAR(20) NOT NULL, title TEXT NOT NULL );"
        )

    yield pool

    with pool.connect() as conn:
        conn.execute(f"DROP TABLE {table_name}")


def test_pooled_connection_with_pytds(pool: sqlalchemy.engine.Engine) -> None:
    insert_stmt = sqlalchemy.text(
        f"INSERT INTO {table_name} (id, title) VALUES (:id, :title)",
    )
    with pool.connect() as conn:
        conn.execute(insert_stmt, id="book1", title="Book One")
        conn.execute(insert_stmt, id="book2", title="Book Two")

    select_stmt = sqlalchemy.text(f"SELECT title FROM {table_name} ORDER BY ID;")
    with pool.connect() as conn:
        rows = conn.execute(select_stmt).fetchall()
        titles = [row[0] for row in rows]

    assert titles == ["Book One", "Book Two"]
