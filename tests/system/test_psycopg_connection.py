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
from __future__ import annotations

import asyncio
from datetime import datetime
import os

import pytest
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
    resolver: type[DefaultResolver | DnsResolver] = DefaultResolver,
) -> tuple[sqlalchemy.engine.Engine, Connector]:
    """Creates a connection pool for a Cloud SQL instance and returns the pool
    and the connector.
    """
    connector = Connector(refresh_strategy=refresh_strategy, resolver=resolver)

    # create SQLAlchemy connection pool
    engine = sqlalchemy.create_engine(
        "postgresql+psycopg://",
        creator=lambda: connector.connect(
            instance_connection_name,
            "psycopg",
            user=user,
            password=password,
            db=db,
            ip_type=ip_type,
        ),
    )
    return engine, connector


def test_psycopg_connection() -> None:
    """Basic test to get time from database using psycopg."""
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


def test_lazy_psycopg_connection() -> None:
    """Basic test to get time from database using psycopg and lazy refresh."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type, "lazy"
    )
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()


def test_CAS_psycopg_connection() -> None:
    """Basic test to get time from database using CAS."""
    inst_conn_name = os.environ.get("POSTGRES_CAS_CONNECTION_NAME")
    user = os.environ["POSTGRES_USER"]
    password = os.environ.get("POSTGRES_CAS_PASS")
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    if not inst_conn_name or not password:
        pytest.skip("POSTGRES_CAS_CONNECTION_NAME or POSTGRES_CAS_PASS not set")

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type
    )
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()


def test_customer_managed_CAS_psycopg_connection() -> None:
    """Basic test to get time from database using Customer Managed CAS."""
    inst_conn_name = os.environ.get("POSTGRES_CUSTOMER_CAS_CONNECTION_NAME")
    user = os.environ["POSTGRES_USER"]
    password = os.environ.get("POSTGRES_CUSTOMER_CAS_PASS")
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    if not inst_conn_name or not password:
        pytest.skip("POSTGRES_CUSTOMER_CAS_CONNECTION_NAME or POSTGRES_CUSTOMER_CAS_PASS not set")

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type
    )
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()


def test_custom_SAN_with_dns_psycopg_connection() -> None:
    """Basic test to get time from database using Custom SAN with DNS."""
    inst_conn_name = os.environ.get("POSTGRES_CUSTOMER_CAS_PASS_VALID_DOMAIN_NAME")
    user = os.environ["POSTGRES_USER"]
    password = os.environ.get("POSTGRES_CUSTOMER_CAS_PASS")
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    if not inst_conn_name or not password:
        pytest.skip("POSTGRES_CUSTOMER_CAS_PASS_VALID_DOMAIN_NAME or POSTGRES_CUSTOMER_CAS_PASS not set")

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type, resolver=DnsResolver
    )
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()


def test_MCP_psycopg_connection() -> None:
    """Basic test to get time from database using MCP enabled instance."""
    inst_conn_name = os.environ.get("POSTGRES_MCP_CONNECTION_NAME")
    user = os.environ["POSTGRES_USER"]
    password = os.environ.get("POSTGRES_MCP_PASS")
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    if not inst_conn_name or not password:
        pytest.skip("POSTGRES_MCP_CONNECTION_NAME or POSTGRES_MCP_PASS not set")

    engine, connector = create_sqlalchemy_engine(
        inst_conn_name, user, password, db, ip_type
    )
    with engine.connect() as conn:
        time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
        conn.commit()
        curr_time = time[0]
        assert type(curr_time) is datetime
    connector.close()


def test_system_psycopg_to_thread() -> None:
    """Verify that running sync connect in asyncio.to_thread works."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    async def run_connect():
        with Connector() as connector:
            # Run the blocking connector.connect in a thread
            conn = await asyncio.to_thread(
                connector.connect,
                inst_conn_name,
                "psycopg",
                user=user,
                password=password,
                db=db,
                ip_type=ip_type,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT NOW();")
            result = cursor.fetchone()
            assert result is not None
            cursor.close()
            conn.close()

    asyncio.run(run_connect())
