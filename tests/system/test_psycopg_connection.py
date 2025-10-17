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

import asyncio
from datetime import datetime
import os

# [START cloud_sql_connector_postgres_psycopg]
from typing import Union

from psycopg import Connection
import pytest
import logging
import sqlalchemy

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import DefaultResolver
from google.cloud.sql.connector import DnsResolver

SERVER_PROXY_PORT = 3307

logger = logging.getLogger(name=__name__)

# [END cloud_sql_connector_postgres_psycopg]


@pytest.mark.asyncio
async def test_psycopg_connection() -> None:
    """Basic test to get time from database."""
    instance_connection_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    unix_socket_folder = "/tmp/conn"
    unix_socket_path = f"{unix_socket_folder}/.s.PGSQL.3307"

    async with Connector(
        refresh_strategy='lazy', resolver=DefaultResolver
    ) as connector:
        # Open proxy connection
        # start the proxy server
        
        await connector.start_unix_socket_proxy_async(
            instance_connection_name,
            unix_socket_path,
            driver="psycopg",
            user=user,
            password=password,
            db=db,
            ip_type=ip_type,  # can be "public", "private" or "psc"
        )
        
        # Wait for server to start
        await asyncio.sleep(0.5)

        engine = sqlalchemy.create_engine(
            "postgresql+psycopg://",
            creator=lambda: Connection.connect(
                f"host={unix_socket_folder} port={SERVER_PROXY_PORT} dbname={db} user={user} password={password} sslmode=require",
                user=user,
                password=password,
                dbname=db,
                autocommit=True,
            )
        )

        with engine.connect() as conn:
            time = conn.execute(sqlalchemy.text("SELECT NOW()")).fetchone()
            conn.commit()
            curr_time = time[0]
            assert type(curr_time) is datetime
        connector.close()
