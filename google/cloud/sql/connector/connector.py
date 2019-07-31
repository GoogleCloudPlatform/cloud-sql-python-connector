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


def connect(instance_connection_string, driver: str, **kwargs):
    """Prepares and returns a database connection object and starts a
    background thread to refresh the certificates and metadata.

    :type instance_connection_string: str
    :param instance_connection_string:
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

    loop = asyncio.new_event_loop()
    thr = Thread(target=loop.run_forever)
    thr.start()
    icm = InstanceConnectionManager(instance_connection_string, loop)
    return icm.connect(driver, username=kwargs.pop("username"), **kwargs)
