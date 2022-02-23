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
from google.cloud.sql.connector.instance_connection_manager import (
    InstanceConnectionManager,
    IPTypes,
)
from google.cloud.sql.connector.utils import generate_keys
from google.auth.credentials import Credentials
from threading import Thread
from typing import Any, Dict, Optional

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
        self._instances: Dict[str, InstanceConnectionManager] = {}

        # set default params for connections
        self._timeout = timeout
        self._enable_iam_auth = enable_iam_auth
        self._ip_type = ip_type
        self._credentials = credentials

    def connect(
        self, instance_connection_string: str, driver: str, **kwargs: Any
    ) -> Any:
        """Prepares and returns a database connection object and starts a
        background thread to refresh the certificates and metadata.

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

        # Initiate event loop and run in background thread.
        #
        # Create an InstanceConnectionManager object from the connection string.
        # The InstanceConnectionManager should verify arguments.
        #
        # Use the InstanceConnectionManager to establish an SSL Connection.
        #
        # Return a DBAPI connection
        enable_iam_auth = kwargs.pop("enable_iam_auth", self._enable_iam_auth)
        if instance_connection_string in self._instances:
            icm = self._instances[instance_connection_string]
            if enable_iam_auth != icm._enable_iam_auth:
                raise ValueError(
                    f"connect() called with `enable_iam_auth={enable_iam_auth}`, "
                    f"but previously used enable_iam_auth={icm._enable_iam_auth}`. "
                    "If you require both for your use case, please use a new "
                    "connector.Connector object."
                )
        else:
            icm = InstanceConnectionManager(
                instance_connection_string,
                driver,
                self._keys,
                self._loop,
                self._credentials,
                enable_iam_auth,
            )
            self._instances[instance_connection_string] = icm

        if "ip_types" in kwargs:
            ip_type = kwargs.pop("ip_types")
            logger.warning(
                "Deprecation Warning: Parameter `ip_types` is deprecated and may be removed"
                " in a future release. Please use `ip_type` instead."
            )
        else:
            ip_type = kwargs.pop("ip_type", self._ip_type)
        if "timeout" in kwargs:
            return icm.connect(driver, ip_type, **kwargs)
        elif "connect_timeout" in kwargs:
            timeout = kwargs["connect_timeout"]
        else:
            timeout = self._timeout
        try:
            return icm.connect(driver, ip_type, timeout, **kwargs)
        except Exception as e:
            # with any other exception, we attempt a force refresh, then throw the error
            icm.force_refresh()
            raise (e)

    async def _close(self) -> None:
        """Helper function to close InstanceConnectionManagers' tasks."""
        await asyncio.gather(*[icm.close() for icm in self._instances.values()])

    def __del__(self) -> None:
        """Deconstructor to make sure InstanceConnectionManagers are closed
        and tasks have finished to have a graceful exit.
        """
        logger.debug("Entering deconstructor")

        deconstruct_future = asyncio.run_coroutine_threadsafe(
            self._close(), loop=self._loop
        )
        # Will attempt to safely shut down tasks for 5s
        deconstruct_future.result(timeout=5)
        logger.debug("Finished deconstructing")


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
    global _default_connector
    if _default_connector is None:
        _default_connector = Connector()
    return _default_connector.connect(instance_connection_string, driver, **kwargs)
