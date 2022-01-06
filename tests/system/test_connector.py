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
import pymysql
import sqlalchemy
import logging
import google.auth
from google.cloud.sql.connector import connector

table_name = f"books_{uuid.uuid4().hex}"


def init_connection_engine(
    custom_connector: connector.Connector,
) -> sqlalchemy.engine.Engine:
    conn: pymysql.connections.Connection = lambda: custom_connector.connect(
        os.environ["MYSQL_CONNECTION_NAME"],
        "pymysql",
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASS"],
        db=os.environ["MYSQL_DB"],
    )

    engine = sqlalchemy.create_engine(
        "mysql+pymysql://",
        creator=conn,
    )
    return engine


def test_connector_with_credentials() -> None:
    """Test Connector object connection with credentials loaded from file."""
    credentials, project = google.auth.load_credentials_from_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    )
    print(type(credentials))
    custom_connector = connector.Connector(credentials=credentials)
    try:
        pool = init_connection_engine(custom_connector)

        with pool.connect() as conn:
            conn.execute("SELECT 1")

    except Exception as e:
        logging.exception("Failed to connect with credentials from file!", e)
