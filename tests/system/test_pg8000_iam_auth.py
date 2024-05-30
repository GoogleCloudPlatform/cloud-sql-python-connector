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
from typing import Generator

import pg8000
import pytest
import sqlalchemy

from google.cloud.sql.connector import Connector


# The Cloud SQL Python Connector can be used along with SQLAlchemy using the
# 'creator' argument to 'create_engine'
def init_connection_engine(connector: Connector) -> sqlalchemy.engine.Engine:
    # initialize Connector object for connections to Cloud SQL
    def getconn() -> pg8000.dbapi.Connection:
        conn: pg8000.dbapi.Connection = connector.connect(
            os.environ["POSTGRES_IAM_CONNECTION_NAME"],
            "pg8000",
            user=os.environ["POSTGRES_IAM_USER"],
            db=os.environ["POSTGRES_DB"],
            enable_iam_auth=True,
        )
        return conn

    # create SQLAlchemy connection pool
    pool = sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    pool.dialect.description_encoding = None
    return pool


@pytest.fixture
def pool() -> Generator:
    connector = Connector()
    pool = init_connection_engine(connector)

    yield pool

    connector.close()


@pytest.fixture
def lazy_pool() -> Generator:
    connector = Connector(refresh_strategy="lazy")
    pool = init_connection_engine(connector)

    yield pool

    connector.close()


def test_pooled_connection_with_pg8000_iam_auth(
    pool: sqlalchemy.engine.Engine,
) -> None:
    with pool.connect() as conn:
        result = conn.execute(sqlalchemy.text("SELECT 1;")).fetchone()
        assert isinstance(result[0], int)
        assert result[0] == 1


def test_lazy_connection_with_pg8000_iam_auth(
    lazy_pool: sqlalchemy.engine.Engine,
) -> None:
    with lazy_pool.connect() as conn:
        result = conn.execute(sqlalchemy.text("SELECT 1;")).fetchone()
        assert isinstance(result[0], int)
        assert result[0] == 1
