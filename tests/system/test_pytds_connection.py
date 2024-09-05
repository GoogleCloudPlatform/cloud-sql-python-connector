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
from typing import Tuple

# [START cloud_sql_connector_mysql_pytds]
import pytds
import sqlalchemy

from google.cloud.sql.connector import Connector


def create_sqlalchemy_engine(
    instance_connection_name: str,
    user: str,
    password: str,
    db: str,
    refresh_strategy: str = "background",
) -> Tuple[sqlalchemy.engine.Engine, Connector]:
    """Creates a connection pool for a Cloud SQL instance and returns the pool
    and the connector. Callers are responsible for closing the pool and the
    connector.

    A sample invocation looks like:

        engine, connector = create_sqlalchemy_engine(
            inst_conn_name,
            user,
            password,
            db,
        )
        with engine.connect() as conn:
            data = conn.execute(sqlalchemy.text("SELECT 1")).fetchone()
            conn.commit()
            # do something with query result
            connector.close()

    Args:
        instance_connection_name (str):
            The instance connection name specifies the instance relative to the
            project and region. For example: "my-project:my-region:my-instance"
        user (str):
            The database user name, e.g., sqlserver
        password (str):
            The database user's password, e.g., secret-password
        db (str):
            The name of the database, e.g., mydb
        refresh_strategy (Optional[str]):
            Refresh strategy for the Cloud SQL Connector. Can be one of "lazy"
            or "background". For serverless environments use "lazy" to avoid
            errors resulting from CPU being throttled.
    """
    connector = Connector(refresh_strategy=refresh_strategy)

    def getconn() -> pytds.Connection:
        conn: pytds.Connection = connector.connect(
            instance_connection_name,
            "pytds",
            user=user,
            password=password,
            db=db,
            ip_type="public",  # can also be "private" or "psc"
        )
        return conn

    # create SQLAlchemy connection pool
    engine = sqlalchemy.create_engine(
        "mssql+pytds://",
        creator=getconn,
    )
    return engine, connector


# [END cloud_sql_connector_mysql_pytds]


def test_pytds_connection() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["SQLSERVER_CONNECTION_NAME"]
    user = os.environ["SQLSERVER_USER"]
    password = os.environ["SQLSERVER_PASS"]
    db = os.environ["SQLSERVER_DB"]

    engine, connector = create_sqlalchemy_engine(inst_conn_name, user, password, db)
    with engine.connect() as conn:
        res = conn.execute(sqlalchemy.text("SELECT 1")).fetchone()
        conn.commit()
        assert res[0] == 1
    connector.close()


def test_lazy_pytds_connection() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["SQLSERVER_CONNECTION_NAME"]
    user = os.environ["SQLSERVER_USER"]
    password = os.environ["SQLSERVER_PASS"]
    db = os.environ["SQLSERVER_DB"]

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, password, db, "lazy"
    )
    with engine.connect() as conn:
        res = conn.execute(sqlalchemy.text("SELECT 1")).fetchone()
        conn.commit()
        assert res[0] == 1
    connector.close()
