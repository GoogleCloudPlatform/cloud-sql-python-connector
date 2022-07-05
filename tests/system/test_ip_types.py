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
import logging
import os
import uuid

import pymysql
import pytest
import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes

table_name = f"books_{uuid.uuid4().hex}"


def init_connection_engine(
    connector: Connector, ip_type: IPTypes
) -> sqlalchemy.engine.Engine:
    def getconn() -> pymysql.connections.Connection:
        conn: pymysql.connections.Connection = connector.connect(
            os.environ["MYSQL_CONNECTION_NAME"],
            "pymysql",
            ip_type=ip_type,
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


def test_public_ip() -> None:
    with Connector() as connector:
        try:
            pool = init_connection_engine(connector, IPTypes.PUBLIC)
        except Exception as e:
            logging.exception("Failed to initialize pool with public IP", e)
        with pool.connect() as conn:
            conn.execute("SELECT 1")


@pytest.mark.private_ip
def test_private_ip() -> None:
    with Connector() as connector:
        try:
            pool = init_connection_engine(connector, IPTypes.PRIVATE)
        except Exception as e:
            logging.exception("Failed to initialize pool with private IP", e)
        with pool.connect() as conn:
            conn.execute("SELECT 1")
