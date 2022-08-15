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

from typing import Any
from enum import Enum

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.util import await_only
from google.cloud.sql.connector import Connector, IPTypes


class SQLAlchemyURL(Enum):
    """Enum class for SQLAlchemy database connection URLs"""

    asyncpg = "postgresql+asyncpg://"
    pg8000 = "postgresql+pg8000://"
    pymysql = "mysql+pymysql://"
    pytds = "mssql+pytds://localhost"


async def async_creator(
    instance_connection_name: str,
    driver: str,
    user: str,
    password: str,
    db: str,
    ip_type: IPTypes,
    enable_iam_auth: bool,
    **connect_args: Any
) -> Any:
    """
    Asynchronous creator function to create SQLAlchemy connection pool.

    Args:

    """
    loop = asyncio.get_running_loop()
    # create connector object to be used with connection pool
    async with Connector(
        ip_type=ip_type, enable_iam_auth=enable_iam_auth, loop=loop
    ) as connector:
        conn = await connector.connect_async(
            instance_connection_name,
            driver,
            user=user,
            password=password,
            db=db,
            **connect_args,
        )
        return conn


async def create_async_pool(instance_connection_name, driver, **kwargs):
    """
    Prepare and return an async SQLAlchemy connection pool using the Cloud SQL Python Connector.

    :type instance_connection_string: str
    :param instance_connection_string:
        A string containing the GCP project name, region name, and instance
        name separated by colons.

        Example: project:us-central1:example-instance

    :type driver: str
    :param: driver:
        A string representing the driver to connect with. Supported driver is
        asyncpg.

    :type user: str
    :param: user:
        Database user to connect with.

    :type password: str
    :param: password:
        Database password for the database user.

    :type db: str
    :param: db:
        Name of database on Cloud SQL instance to connect to.

    :type ip_type: IPTypes
    :param ip_type
        The IP type (public or private) used to connect. IPTypes
        can be either IPTypes.PUBLIC or IPTypes.PRIVATE.

    :type enable_iam_auth: bool
    :param enable_iam_auth
        Enables automatic IAM based authentication (Postgres only).

    :type connect_args: dict
    :param connect_args
        Pass in any driver-specific arguments needed (as dict)
        to connect to the Cloud SQL instance.

    :param kwargs:
        Pass in any `sqlalchemy.create_engine` specific arguments to
        configure connection pool.

    :rtype: `sqlalchemy.ext.asyncio.engine.AsyncEngine`
    :returns:
        A SQLAlchemy connection pool engine.
    """
    user = kwargs.pop("user")
    password = kwargs.pop("password", "")
    db = kwargs.pop("db")
    ip_type = kwargs.pop("ip_type", IPTypes.PUBLIC)
    enable_iam_auth = kwargs.pop("enable_iam_auth", False)
    connect_args = kwargs.pop("connect_args", {})

    def adapted_creator():
        """Helper function to be used as synchronous creator function with `sqlalchemy.create_async_engine`"""
        dbapi = engine.dialect.dbapi
        from sqlalchemy.dialects.postgresql.asyncpg import (
            AsyncAdapt_asyncpg_connection,
        )

        return AsyncAdapt_asyncpg_connection(
            dbapi,
            await_only(
                async_creator(
                    instance_connection_name,
                    driver,
                    user,
                    password,
                    db,
                    ip_type,
                    enable_iam_auth,
                    **connect_args,
                )
            ),
            prepared_statement_cache_size=100,
        )

    database_url = SQLAlchemyURL[driver]
    # create async connection pool with wrapped creator
    engine = create_async_engine(database_url.value, creator=adapted_creator, **kwargs)
    return engine


def create_pool(instance_connection_name, driver, **kwargs):
    """
    Prepare and return a SQLAlchemy connection pool using the Cloud SQL Python Connector.

    :type instance_connection_string: str
    :param instance_connection_string:
        A string containing the GCP project name, region name, and instance
        name separated by colons.

        Example: project:us-central1:example-instance

    :type driver: str
    :param: driver:
        A string representing the driver to connect with. Supported driver is
        asyncpg.

    :type user: str
    :param: user:
        Database user to connect with.

    :type password: str
    :param: password:
        Database password for the database user.

    :type db: str
    :param: db:
        Name of database on Cloud SQL instance to connect to.

    :type ip_type: IPTypes
    :param ip_type
        The IP type (public or private) used to connect. IPTypes
        can be either IPTypes.PUBLIC or IPTypes.PRIVATE.

    :type enable_iam_auth: bool
    :param enable_iam_auth
        Enables automatic IAM based authentication (Postgres only).

    :type connect_args: dict
    :param connect_args
        Pass in any driver-specific arguments needed (as dict)
        to connect to the Cloud SQL instance.

    :param kwargs:
        Pass in any `sqlalchemy.create_engine` specific arguments to
        configure connection pool.

    :rtype: `sqlalchemy.engine.base.Engine`
    :returns:
        A SQLAlchemy connection pool engine.
    """
    user = kwargs.pop("user")
    password = kwargs.pop("password", "")
    db = kwargs.pop("db")
    ip_type = kwargs.pop("ip_type", IPTypes.PUBLIC)
    enable_iam_auth = kwargs.pop("enable_iam_auth", False)
    connect_args = kwargs.pop("connect_args", {})

    def creator():
        with Connector(ip_type=ip_type, enable_iam_auth=enable_iam_auth) as connector:
            conn = connector.connect(
                instance_connection_name,
                driver,
                user=user,
                password=password,
                db=db,
                **connect_args,
            )
            return conn

    database_url = SQLAlchemyURL[driver]
    engine = create_engine(database_url.value, creator=creator, **kwargs)
    return engine
