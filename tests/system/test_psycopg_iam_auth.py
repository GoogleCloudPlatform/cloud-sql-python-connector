"""
Copyright 2026 Google LLC

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

import pytest
import sqlalchemy

from google.cloud.sql.connector import Connector

# Skip all tests in this file if POSTGRES_IAM_USER is not set
pytestmark = pytest.mark.skipif(
    not os.environ.get("POSTGRES_IAM_USER"),
    reason="POSTGRES_IAM_USER env var not set for IAM Authn tests",
)


def create_sqlalchemy_engine(
    instance_connection_name: str,
    user: str,
    db: str,
    ip_type: str = "public",
    refresh_strategy: str = "background",
) -> tuple[sqlalchemy.engine.Engine, Connector]:
    """Creates a connection pool for a Cloud SQL instance and returns the pool
    and the connector.
    """
    connector = Connector(refresh_strategy=refresh_strategy)

    # create SQLAlchemy connection pool
    engine = sqlalchemy.create_engine(
        "postgresql+psycopg://",
        creator=lambda: connector.connect(
            instance_connection_name,
            "psycopg",
            user=user,
            db=db,
            ip_type=ip_type,
            enable_iam_auth=True,
        ),
    )
    return engine, connector


def test_psycopg_iam_authn_connection() -> None:
    """Basic test to get time from database using psycopg and IAM Authn."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_IAM_USER"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.getenv("IP_TYPE", "public")

    engine, connector = create_sqlalchemy_engine(inst_conn_name, user, db, ip_type)
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()


def test_lazy_psycopg_iam_authn_connection() -> None:
    """Basic test to get time from database using psycopg, IAM Authn and lazy refresh."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_IAM_USER"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.getenv("IP_TYPE", "public")

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, db, ip_type, refresh_strategy="lazy"
    )
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()
