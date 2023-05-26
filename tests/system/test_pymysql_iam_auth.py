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
import os
from typing import Generator
import uuid

import pymysql
import pytest
import sqlalchemy

from google.cloud.sql.connector import Connector

table_name = f"books_{uuid.uuid4().hex}"


# [START cloud_sql_connector_mysql_pymysql_iam_auth]
# The Cloud SQL Python Connector can be used along with SQLAlchemy using the
# 'creator' argument to 'create_engine'
def init_connection_engine() -> sqlalchemy.engine.Engine:
    def getconn() -> pymysql.connections.Connection:
        # initialize Connector object for connections to Cloud SQL
        with Connector() as connector:
            conn: pymysql.connections.Connection = connector.connect(
                os.environ["MYSQL_IAM_CONNECTION_NAME"],
                "pymysql",
                user=os.environ["MYSQL_IAM_USER"],
                db=os.environ["MYSQL_DB"],
                enable_iam_auth=True,
            )
            return conn

    # create SQLAlchemy connection pool
    pool = sqlalchemy.create_engine(
        "mysql+pymysql://",
        creator=getconn,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    return pool


# [END cloud_sql_connector_mysql_pymysql_iam_auth]


@pytest.fixture(name="pool")
def setup() -> Generator:
    pool = init_connection_engine()

    with pool.connect() as conn:
        conn.execute(
            sqlalchemy.text(
                f"CREATE TABLE IF NOT EXISTS {table_name}"
                " ( id CHAR(20) NOT NULL, title TEXT NOT NULL );"
            )
        )

    yield pool

    with pool.connect() as conn:
        conn.execute(sqlalchemy.text(f"DROP TABLE IF EXISTS {table_name}"))


def test_pooled_connection_with_pymysql_iam_auth(
    pool: sqlalchemy.engine.Engine,
) -> None:
    insert_stmt = sqlalchemy.text(
        f"INSERT INTO {table_name} (id, title) VALUES (:id, :title)",
    )
    with pool.connect() as conn:
        conn.execute(insert_stmt, parameters={"id": "book1", "title": "Book One"})
        conn.execute(insert_stmt, parameters={"id": "book2", "title": "Book Two"})

    select_stmt = sqlalchemy.text(f"SELECT title FROM {table_name} ORDER BY ID;")
    with pool.connect() as conn:
        rows = conn.execute(select_stmt).fetchall()
        titles = [row[0] for row in rows]

    assert titles == ["Book One", "Book Two"]
