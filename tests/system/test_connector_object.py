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
import asyncio
import concurrent.futures
import datetime
import logging
import os
from threading import Thread

import google.auth
import pymysql
import pytest
import sqlalchemy

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector.exceptions import AutoIAMAuthNotSupported


def init_connection_engine(
    custom_connector: Connector,
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

    pool = sqlalchemy.create_engine(
        "mysql+pymysql://",
        creator=getconn,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    return pool


def test_connector_with_credentials() -> None:
    """Test Connector object connection with credentials loaded from file."""
    credentials, _ = google.auth.load_credentials_from_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    )
    custom_connector = Connector(credentials=credentials)
    try:
        pool = init_connection_engine(custom_connector)

        with pool.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))

    except Exception as e:
        logging.exception("Failed to connect with credentials from file!", e)
    # close connector
    custom_connector.close()


def test_multiple_connectors() -> None:
    """Test that same Cloud SQL instance can connect with two Connector objects."""
    first_connector = Connector()
    second_connector = Connector()
    try:
        pool = init_connection_engine(first_connector)
        pool2 = init_connection_engine(second_connector)

        with pool.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))

        with pool2.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))

        instance_connection_string = os.environ["MYSQL_CONNECTION_NAME"]
        assert instance_connection_string in first_connector._cache
        assert instance_connection_string in second_connector._cache
        assert (
            first_connector._cache[instance_connection_string]
            != second_connector._cache[instance_connection_string]
        )
    except Exception as e:
        logging.exception("Failed to connect with multiple Connector objects!", e)

    # close connectors
    first_connector.close()
    second_connector.close()


def test_connector_in_ThreadPoolExecutor() -> None:
    """Test that Connector can connect from ThreadPoolExecutor thread.
    This helps simulate how connector works in Cloud Run and Cloud Functions.
    """

    def get_time() -> datetime.datetime:
        """Helper method for getting current time from database."""
        default_connector = Connector()
        pool = init_connection_engine(default_connector)

        # connect to database and get current time
        with pool.connect() as conn:
            current_time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()

        # close connector
        default_connector.close()
        return current_time[0]

    # try running connector in ThreadPoolExecutor as Cloud Run does
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(get_time)
        return_value = future.result()
        assert isinstance(return_value, datetime.datetime)


def test_connector_as_context_manager() -> None:
    """Test that Connector can be used as a context manager."""
    with Connector() as connector:
        pool = init_connection_engine(connector)

        with pool.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))


def test_connector_with_custom_loop() -> None:
    """Test that Connector can be used with custom loop in background thread."""
    # create new event loop and start it in thread
    loop = asyncio.new_event_loop()
    thread = Thread(target=loop.run_forever, daemon=True)
    thread.start()

    with Connector(loop=loop) as connector:
        pool = init_connection_engine(connector)

        with pool.connect() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchone()
        assert result[0] == 1
        # assert that Connector does not start its own thread
        assert connector._thread is None


def test_connector_sqlserver_iam_auth_error() -> None:
    """
    Test that connecting with enable_iam_auth set to True
    for SQL Server raises exception.
    """
    with pytest.raises(AutoIAMAuthNotSupported):
        with Connector(enable_iam_auth=True) as connector:
            connector.connect(
                os.environ["SQLSERVER_CONNECTION_NAME"],
                "pytds",
                user="my-user",
                password="my-pass",
                db="my-db",
            )
