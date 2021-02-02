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

import pytest
import sqlalchemy
from google.cloud.sql.connector import connector

table_name = f"books_{uuid.uuid4().hex}"


def init_connection_engine():
    def getconn():
        conn = connector.connect(
            os.environ["MYSQL_CONNECTION_NAME"],
            "pymysql",
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASS"],
            db=os.environ["MYSQL_DB"],
        )
        return conn

    engine = sqlalchemy.create_engine(
        "mysql+pymysql://",
        creator=getconn,
    )
    return engine


@pytest.fixture(name="pool")
def setup():
    pool = init_connection_engine()

    with pool.connect() as conn:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS `{table_name}`"
            " ( id CHAR(20) NOT NULL, title TEXT NOT NULL );"
        )

    yield pool

    with pool.connect() as conn:
        conn.execute(f"DROP TABLE IF EXISTS `{table_name}`")


def test_pooled_connection_with_pymysql(pool):
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
