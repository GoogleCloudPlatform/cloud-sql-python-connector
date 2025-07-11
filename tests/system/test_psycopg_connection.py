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

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import DefaultResolver

from sqlalchemy.dialects.postgresql.base import PGDialect
PGDialect._get_server_version_info = lambda *args: (9, 2)

# [END cloud_sql_connector_postgres_psycopg]


def test_psycopg_connection() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASS"]
    db = os.environ["POSTGRES_DB"]
    ip_type = os.environ.get("IP_TYPE", "public")

    connector = Connector(refresh_strategy="background", resolver=DefaultResolver)

    pool = connector.connect(
        inst_conn_name,
        "psycopg",
        user=user,
        password=password,
        db=db,
        ip_type=ip_type,  # can be "public", "private" or "psc"
    )

    with pool as conn:

        # Open a cursor to perform database operations
        with conn.cursor() as cur:

            # Query the database and obtain data as Python objects.
            cur.execute("SELECT NOW()")
            curr_time = cur.fetchone()["now"]
            assert type(curr_time) is datetime


