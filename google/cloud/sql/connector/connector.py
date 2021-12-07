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

from threading import Thread
from typing import Any, Dict, Optional

logger = logging.getLogger(name=__name__)

class Connector():
    def __init__(self, **cfg):
        # This thread is used to background processing
        self._thread: Optional[Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._keys: Optional[concurrent.futures.Future] = None
        self._instances: Dict[str, InstanceConnectionManager] = {}

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._thread = Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()
        return self._loop

    def _get_keys(self, loop: asyncio.AbstractEventLoop) -> concurrent.futures.Future:
        if self._keys is None:
            self._keys = asyncio.run_coroutine_threadsafe(generate_keys(), loop)
        return self._keys

    def connect(
        self,
        instance_connection_string: str,
        driver: str,
        ip_types: IPTypes = IPTypes.PUBLIC,
        enable_iam_auth: bool = False,
        **kwargs: Any
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

        :type ip_types: IPTypes
            The IP type (public or private)  used to connect. IP types
            can be either IPTypes.PUBLIC or IPTypes.PRIVATE.

        :param enable_iam_auth
        Enables IAM based authentication (Postgres only).
        :type enable_iam_auth: bool

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

        loop = self._get_loop()
        if instance_connection_string in self._instances:
            icm = self._instances[instance_connection_string]
        else:
            keys = self._get_keys(loop)
            icm = InstanceConnectionManager(
                instance_connection_string, driver, keys, loop, enable_iam_auth
            )
            self._instances[instance_connection_string] = icm

        if "timeout" in kwargs:
            return icm.connect(driver, ip_types, **kwargs)
        elif "connect_timeout" in kwargs:
            timeout = kwargs["connect_timeout"]
        else:
            timeout = 30  # 30s
        try:
            return icm.connect(driver, ip_types, timeout, **kwargs)
        except Exception as e:
            # with any other exception, we attempt a force refresh, then throw the error
            icm.force_refresh()
            raise (e)

_default_connector: Optional[Connector] = None

def connect(
    instance_connection_string: str,
    driver: str,
    ip_types: IPTypes = IPTypes.PUBLIC,
    enable_iam_auth: bool = False,
    **kwargs: Any
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

    :type ip_types: IPTypes
        The IP type (public or private)  used to connect. IP types
        can be either IPTypes.PUBLIC or IPTypes.PRIVATE.

    :param enable_iam_auth
    Enables IAM based authentication (Postgres only).
    :type enable_iam_auth: bool

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
    return _default_connector.connect(instance_connection_string, driver, ip_types, enable_iam_auth, **kwargs)
