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
import pymysql
import sqlalchemy
import logging
import google.auth
from google.cloud.sql.connector import connector
import datetime
import concurrent.futures


def init_connection_engine(
    custom_connector: connector.Connector,
) -> sqlalchemy.engine.Engine:
    def getconn() -> pymysql.connections.Connection:
        conn = custom_connector.connect(
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


def test_connector_with_credentials() -> None:
    """Test Connector object connection with credentials loaded from file."""
    credentials, project = google.auth.load_credentials_from_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    )
    custom_connector = connector.Connector(credentials=credentials)
    try:
        pool = init_connection_engine(custom_connector)

        with pool.connect() as conn:
            conn.execute("SELECT 1")

    except Exception as e:
        logging.exception("Failed to connect with credentials from file!", e)


def test_multiple_connectors() -> None:
    """Test that same Cloud SQL instance can connect with two Connector objects."""
    first_connector = connector.Connector()
    second_connector = connector.Connector()
    try:
        pool = init_connection_engine(first_connector)
        pool2 = init_connection_engine(second_connector)

        with pool.connect() as conn:
            conn.execute("SELECT 1")

        with pool2.connect() as conn:
            conn.execute("SELECT 1")

        instance_connection_string = os.environ["MYSQL_CONNECTION_NAME"]
        assert instance_connection_string in first_connector._instances
        assert instance_connection_string in second_connector._instances
        assert (
            first_connector._instances[instance_connection_string]
            != second_connector._instances[instance_connection_string]
        )
    except Exception as e:
        logging.exception("Failed to connect with multiple Connector objects!", e)


def test_connector_in_ThreadPoolExecutor() -> None:
    """Test that Connector can connect from ThreadPoolExecutor thread.
    This helps simulate how connector works in Cloud Run and Cloud Functions.
    """

    def get_time() -> datetime.datetime:
        """Helper method for getting current time from database."""
        default_connector = connector.Connector()
        pool = init_connection_engine(default_connector)

        # connect to database and get current time
        with pool.connect() as conn:
            current_time = conn.execute("SELECT NOW()").fetchone()
        return current_time[0]

    # try running connector in ThreadPoolExecutor as Cloud Run does
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(get_time)
        return_value = future.result()
        assert isinstance(return_value, datetime.datetime)
