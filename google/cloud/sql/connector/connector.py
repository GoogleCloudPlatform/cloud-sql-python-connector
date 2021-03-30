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
from google.cloud.sql.connector.InstanceConnectionManager import (
    InstanceConnectionManager,
)

from threading import Thread
from typing import Optional


# This thread is used to background processing
_thread: Optional[Thread] = None
_loop: Optional[asyncio.AbstractEventLoop] = None

_instances = {}

def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        _thread = Thread(target=_loop.run_forever, daemon=True)
        _thread.start()
    return _loop


def connect(instance_conn_str, driver: str, **kwargs):
    """Prepares and returns a database connection object and starts a
    background thread to refresh the certificates and metadata.

    :type instance_conn_str: str
    :param instance_conn_str:
        A string containing the GCP project name, region name, and instance
        name separated by colons.

        Example: example-proj:example-region-us6:example-instance

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

    loop = _get_loop()
    if instance_conn_str in _instances:
        icm = _instances[instance_conn_str]
    else:
        icm = InstanceConnectionManager(instance_conn_str, driver, loop)
        _instances[instance_conn_str] = icm
            

    return icm.connect(driver, user=kwargs.pop("user"), **kwargs)
