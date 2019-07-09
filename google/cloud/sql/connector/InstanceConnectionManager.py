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
from google.auth.credentials import Credentials


class CloudSQLConnectionStringError(Exception):
    """
    Raised when the provided connection string is not formatted
    correctly.
    """

    def __init__(self, *args, **kwargs) -> None:
        Exception.__init__(self, *args, **kwargs)


class InstanceConnectionManager:
    """A class to manage the details of the connection, including refreshing the
    credentials.

    :param instance_connection_string:
        The Google Cloud SQL Instance's connection
        string.
    :type instance_connection_string: str
    :param loop:
        A new event loop for the refresh function to run in.
    :type loop: asyncio.unix_events._UnixSelectorEventLoop
    """
    _instance_connection_string: str = None
    _loop: asyncio.unix_events._UnixSelectorEventLoop = None
    _project: str = None
    _region: str = None
    _instance: str = None
    _credentials: Credentials = None

    def __init__(
        self,
        instance_connection_string: str,
        loop: asyncio.unix_events._UnixSelectorEventLoop,
    ) -> None:
        # Validate connection string
        connection_string_split = instance_connection_string.split(":")

        if len(connection_string_split) == 3:
            self.instance_connection_string = instance_connection_string
            self.project = connection_string_split[1]
            self.instance = connection_string_split[2]
        else:
            raise CloudSQLConnectionStringError(
                "Arg instance_connection_string must be in "
                + "format: project:region:instance."
            )

        # set current to future InstanceMetadata
        # set next to the future future InstanceMetadata
