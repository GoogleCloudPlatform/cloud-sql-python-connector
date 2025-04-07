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

from datetime import datetime
import os

import sqlalchemy

from google.cloud.sql.connector import Connector


def create_sqlalchemy_engine(
    instance_connection_name: str,
    user: str,
    db: str,
    ip_type: str = "public",
    refresh_strategy: str = "background",
) -> tuple[sqlalchemy.engine.Engine, Connector]:
    """Creates a connection pool for a Cloud SQL instance and returns the pool
    and the connector. Callers are responsible for closing the pool and the
    connector.

    A sample invocation looks like:

        engine, connector = create_sqlalchemy_engine(
            inst_conn_name,
            user,
            db,
        )
        with engine.connect() as conn:
            time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
            conn.commit()
            curr_time = time[0]
            # do something with query result
            connector.close()

    Args:
        instance_connection_name (str):
            The instance connection name specifies the instance relative to the
            project and region. For example: "my-project:my-region:my-instance"
        user (str):
            The formatted IAM database username. (truncate everything after '@')
            e.g., my-email@test.com -> my-email
        db (str):
            The name of the database, e.g., mydb
        ip_type (str):
            The IP type of the Cloud SQL instance to connect to. Can be one
            of "public", "private", or "psc".
        refresh_strategy (Optional[str]):
            Refresh strategy for the Cloud SQL Connector. Can be one of "lazy"
            or "background". For serverless environments use "lazy" to avoid
            errors resulting from CPU being throttled.
    """
    connector = Connector(refresh_strategy=refresh_strategy)

    # create SQLAlchemy connection pool
    engine = sqlalchemy.create_engine(
        "mysql+pymysql://",
        creator=lambda: connector.connect(
            instance_connection_name,
            "pymysql",
            user=user,
            db=db,
            ip_type=ip_type,  # can be "public", "private" or "psc"
            enable_iam_auth=True,
        ),
    )
    return engine, connector


def test_pymysql_iam_authn_connection() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["MYSQL_CONNECTION_NAME"]
    user = os.environ["MYSQL_IAM_USER"]
    db = os.environ["MYSQL_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    engine, connector = create_sqlalchemy_engine(inst_conn_name, user, db, ip_type)
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()


def test_lazy_pymysql_iam_authn_connection() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["MYSQL_CONNECTION_NAME"]
    user = os.environ["MYSQL_IAM_USER"]
    db = os.environ["MYSQL_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, db, ip_type, "lazy"
    )
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()


def test_MCP_pymysql_iam_authn_connection() -> None:
    """Basic test to get time from database using MCP enabled instance."""
    inst_conn_name = os.environ["MYSQL_MCP_CONNECTION_NAME"]
    user = os.environ["MYSQL_IAM_USER"]
    db = os.environ["MYSQL_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    engine, connector = create_sqlalchemy_engine(inst_conn_name, user, db, ip_type)
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()
