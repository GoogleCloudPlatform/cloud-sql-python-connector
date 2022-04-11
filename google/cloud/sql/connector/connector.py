"""
Copyright 2019 Google LLC

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
import concurrent
import logging
from types import TracebackType
from google.cloud.sql.connector.instance import (
    Instance,
    IPTypes,
)
import google.cloud.sql.connector.pymysql as pymysql
import google.cloud.sql.connector.pg8000 as pg8000
import google.cloud.sql.connector.pytds as pytds
from google.cloud.sql.connector.utils import generate_keys
from google.auth.credentials import Credentials
from threading import Thread
from typing import Any, Dict, Optional, Type
from functools import partial

logger = logging.getLogger(name=__name__)

_default_connector = None


class Connector:
    """A class to configure and create connections to Cloud SQL instances.

    :type ip_type: IPTypes
    :param ip_type
        The IP type (public or private)  used to connect. IP types
        can be either IPTypes.PUBLIC or IPTypes.PRIVATE.

    :type enable_iam_auth: bool
    :param enable_iam_auth
        Enables IAM based authentication (Postgres only).

    :type timeout: int
    :param timeout
        The time limit for a connection before raising a TimeoutError.

    :type credentials: google.auth.credentials.Credentials
    :param credentials
        Credentials object used to authenticate connections to Cloud SQL server.
        If not specified, Application Default Credentials are used.
    """

    def __init__(
        self,
        ip_type: IPTypes = IPTypes.PUBLIC,
        enable_iam_auth: bool = False,
        timeout: int = 30,
        credentials: Optional[Credentials] = None,
    ) -> None:
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._thread: Thread = Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._keys: concurrent.futures.Future = asyncio.run_coroutine_threadsafe(
            generate_keys(), self._loop
        )
        self._instances: Dict[str, Instance] = {}

        # set default params for connections
        self._timeout = timeout
        self._enable_iam_auth = enable_iam_auth
        self._ip_type = ip_type
        self._credentials = credentials

    def connect(
        self, instance_connection_string: str, driver: str, **kwargs: Any
    ) -> Any:
        """Prepares and returns a database connection object and starts a
        background task to refresh the certificates and metadata.

        :type instance_connection_string: str
        :param instance_connection_string:
            A string containing the GCP project name, region name, and instance
            name separated by colons.

            Example: example-proj:example-region-us6:example-instance

        :type driver: str
        :param: driver:
            A string representing the driver to connect with. Supported drivers are
            pymysql, pg8000, and pytds.

        :param kwargs:
            Pass in any driver-specific arguments needed to connect to the Cloud
            SQL instance.

        :rtype: Connection
        :returns:
            A DB-API connection to the specified Cloud SQL instance.
        """
        connect_task = asyncio.run_coroutine_threadsafe(
            self.connect_async(instance_connection_string, driver, **kwargs), self._loop
        )
        return connect_task.result()

    async def connect_async(
        self, instance_connection_string: str, driver: str, **kwargs: Any
    ) -> Any:
        """Prepares and returns a database connection object and starts a
        background task to refresh the certificates and metadata.

        :type instance_connection_string: str
        :param instance_connection_string:
            A string containing the GCP project name, region name, and instance
            name separated by colons.

            Example: example-proj:example-region-us6:example-instance

        :type driver: str
        :param: driver:
            A string representing the driver to connect with. Supported drivers are
            pymysql, pg8000, and pytds.

        :param kwargs:
            Pass in any driver-specific arguments needed to connect to the Cloud
            SQL instance.

        :rtype: Connection
        :returns:
            A DB-API connection to the specified Cloud SQL instance.
        """

        # Create an Instance object from the connection string.
        # The Instance should verify arguments.
        #
        # Use the Instance to establish an SSL Connection.
        #
        # Return a DBAPI connection
        enable_iam_auth = kwargs.pop("enable_iam_auth", self._enable_iam_auth)
        if instance_connection_string in self._instances:
            instance = self._instances[instance_connection_string]
            if enable_iam_auth != instance._enable_iam_auth:
                raise ValueError(
                    f"connect() called with `enable_iam_auth={enable_iam_auth}`, "
                    f"but previously used enable_iam_auth={instance._enable_iam_auth}`. "
                    "If you require both for your use case, please use a new "
                    "connector.Connector object."
                )
        else:
            instance = Instance(
                instance_connection_string,
                driver,
                self._keys,
                self._loop,
                self._credentials,
                enable_iam_auth,
            )
            self._instances[instance_connection_string] = instance

        connect_func = {
            "pymysql": pymysql.connect,
            "pg8000": pg8000.connect,
            "pytds": pytds.connect,
        }

        # only accept supported database drivers
        try:
            connector = connect_func[driver]
        except KeyError:
            raise KeyError(f"Driver '{driver}' is not supported.")

        if "ip_types" in kwargs:
            ip_type = kwargs.pop("ip_types")
            logger.warning(
                "Deprecation Warning: Parameter `ip_types` is deprecated and may be removed"
                " in a future release. Please use `ip_type` instead."
            )
        else:
            ip_type = kwargs.pop("ip_type", self._ip_type)
        timeout = kwargs.pop("timeout", self._timeout)
        if "connect_timeout" in kwargs:
            timeout = kwargs.pop("connect_timeout")

        # Host and ssl options come from the certificates and metadata, so we don't
        # want the user to specify them.
        kwargs.pop("host", None)
        kwargs.pop("ssl", None)
        kwargs.pop("port", None)

        # helper function to wrap in timeout
        async def get_connection() -> Any:
            instance_data, ip_address = await instance.connect_info(ip_type)
            connect_partial = partial(
                connector, ip_address, instance_data.context, **kwargs
            )
            return await self._loop.run_in_executor(None, connect_partial)

        # attempt to make connection to Cloud SQL instance for given timeout
        try:
            return await asyncio.wait_for(get_connection(), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Connection timed out after {timeout}s")
        except Exception as e:
            # with any other exception, we attempt a force refresh, then throw the error
            instance.force_refresh()
            raise (e)

    def __enter__(self) -> Any:
        """Enter context manager by returning Connector object"""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit context manager by closing Connector"""
        self.close()

    def close(self) -> None:
        """Close Connector by stopping tasks and releasing resources."""
        close_future = asyncio.run_coroutine_threadsafe(self._close(), loop=self._loop)
        # Will attempt to safely shut down tasks for 5s
        close_future.result(timeout=5)

    async def _close(self) -> None:
        """Helper function to cancel Instances' tasks
        and close aiohttp.ClientSession."""
        await asyncio.gather(
            *[instance.close() for instance in self._instances.values()]
        )


def connect(instance_connection_string: str, driver: str, **kwargs: Any) -> Any:
    """Uses a Connector object with default settings and returns a database
    connection object with a background thread to refresh the certificates and metadata.
    For more advanced configurations, callers should instantiate Connector on their own.

    :type instance_connection_string: str
    :param instance_connection_string:
        A string containing the GCP project name, region name, and instance
        name separated by colons.

        Example: example-proj:example-region-us6:example-instance

    :type driver: str
    :param: driver:
        A string representing the driver to connect with. Supported drivers are
        pymysql, pg8000, and pytds.

    :param kwargs:
        Pass in any driver-specific arguments needed to connect to the Cloud
        SQL instance.

    :rtype: Connection
    :returns:
        A DB-API connection to the specified Cloud SQL instance.
    """
    # deprecation warning
    logger.warning(
        "The global `connect` method is deprecated and may be removed in a later "
        "version. Please initialize a `Connector` object and call it's `connect` "
        "method directly. \n"
        "See https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/blob/main/README.md#how-to-use-this-connector for examples.",
    )
    global _default_connector
    if _default_connector is None:
        _default_connector = Connector()
    return _default_connector.connect(instance_connection_string, driver, **kwargs)
