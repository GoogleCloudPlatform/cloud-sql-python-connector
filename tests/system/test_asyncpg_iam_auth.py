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

import asyncio
import os

import sqlalchemy
import sqlalchemy.ext.asyncio

from google.cloud.sql.connector import Connector


async def create_sqlalchemy_engine(
    instance_connection_name: str,
    user: str,
    db: str,
    refresh_strategy: str = "background",
) -> tuple[sqlalchemy.ext.asyncio.engine.AsyncEngine, Connector]:
    """Creates a connection pool for a Cloud SQL instance and returns the pool
    and the connector. Callers are responsible for closing the pool and the
    connector.

    A sample invocation looks like:

        engine, connector = await create_sqlalchemy_engine(
            inst_conn_name,
            user,
            db,
        )
        async with engine.connect() as conn:
            time = (await conn.execute(sqlalchemy.text("SELECT NOW()"))).fetchone()
            curr_time = time[0]
            # do something with query result
            await connector.close_async()

    Args:
        instance_connection_name (str):
            The instance connection name specifies the instance relative to the
            project and region. For example: "my-project:my-region:my-instance"
        user (str):
            The formatted IAM database username.
            e.g., my-email@test.com, service-account@project-id.iam
        db (str):
            The name of the database, e.g., mydb
        refresh_strategy (Optional[str]):
            Refresh strategy for the Cloud SQL Connector. Can be one of "lazy"
            or "background". For serverless environments use "lazy" to avoid
            errors resulting from CPU being throttled.
    """
    loop = asyncio.get_running_loop()
    connector = Connector(loop=loop, refresh_strategy=refresh_strategy)

    # create SQLAlchemy connection pool
    engine = sqlalchemy.ext.asyncio.create_async_engine(
        "postgresql+asyncpg://",
        async_creator=lambda: connector.connect_async(
            instance_connection_name,
            "asyncpg",
            user=user,
            db=db,
            ip_type=os.environ.get(
                "IP_TYPE", "public"
            ),  # can also be "private" or "psc"
            enable_iam_auth=True,
        ),
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    return engine, connector


async def test_iam_authn_connection_with_asyncpg() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_IAM_USER"]
    db = os.environ["POSTGRES_DB"]

    pool, connector = await create_sqlalchemy_engine(inst_conn_name, user, db)

    async with pool.connect() as conn:
        res = (await conn.execute(sqlalchemy.text("SELECT 1"))).fetchone()
        assert res[0] == 1

    await connector.close_async()


async def test_lazy_iam_authn_connection_with_asyncpg() -> None:
    """Basic test to get time from database."""
    inst_conn_name = os.environ["POSTGRES_CONNECTION_NAME"]
    user = os.environ["POSTGRES_IAM_USER"]
    db = os.environ["POSTGRES_DB"]

    pool, connector = await create_sqlalchemy_engine(inst_conn_name, user, db, "lazy")

    async with pool.connect() as conn:
        res = (await conn.execute(sqlalchemy.text("SELECT 1"))).fetchone()
        assert res[0] == 1

    await connector.close_async()
