"""
Copyright 2025 Google LLC

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

# [START cloud_sql_connector_postgres_psycopg]
from typing import Union

from psycopg import Connection
import sqlalchemy

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import DefaultResolver
from google.cloud.sql.connector import DnsResolver


def create_sqlalchemy_engine(
    instance_connection_name: str,
    user: str,
    password: str,
    db: str,
    ip_type: str = "public",
    refresh_strategy: str = "background",
    resolver: Union[type[DefaultResolver], type[DnsResolver]] = DefaultResolver,
) -> tuple[sqlalchemy.engine.Engine, Connector]:
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
            The database user name, e.g., root
        password (str):
            The database user's password, e.g., secret-password
        db (str):
            The name of the database, e.g., mydb
        ip_type (str):
            The IP type of the Cloud SQL instance to connect to. Can be one
            of "public", "private", or "psc".
        refresh_strategy (Optional[str]):
            Refresh strategy for the Cloud SQL Connector. Can be one of "lazy"
            or "background". For serverless environments use "lazy" to avoid
            errors resulting from CPU being throttled.
        resolver (Optional[google.cloud.sql.connector.DefaultResolver]):
            Resolver class for resolving instance connection name. Use
            google.cloud.sql.connector.DnsResolver when resolving DNS domain
            names or google.cloud.sql.connector.DefaultResolver for regular
            instance connection names ("my-project:my-region:my-instance").
    """
    connector = Connector(refresh_strategy=refresh_strategy, resolver=resolver)
    unix_socket_path = "/tmp/conn"
    await connector.start_unix_socket_proxy_async(
        instance_connection_name,
        unix_socket_path,
        ip_type=ip_type,  # can be "public", "private" or "psc"
    )

    # create SQLAlchemy connection pool
    engine = sqlalchemy.create_engine(
        "postgresql+psycopg://",
        creator=lambda: Connection.connect(
            f"host={unix_socket_path} port={SERVER_PROXY_PORT} dbname={db} user={user} password={passwd} sslmode=require",
            user=user,
            password=password,
            db=db,
            autocommit=True,
        )
    )
    
    return engine, connector


# [END cloud_sql_connector_postgres_psycopg]


def test_psycopg_connection() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type
    )
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()
