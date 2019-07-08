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

import re
import asyncio


class CloudSQLConnectionStringError(Exception):
    """
    Raised when the provided connection string is not formatted
    correctly.
    """
    def __init__(self, *args, **kwargs) -> None:
        Exception.__init__(self, *args, **kwargs)


class InstanceConnectionManager:
    _instance_connection_string:str = None
    _loop: asyncio.unix_events._UnixSelectorEventLoop = None
    _project: str = None
    _instance: str = None
    _credentials: google.auth.credentials.Credentials = None

    def __init__(
        self,
        instance_connection_string: str,
        loop: asyncio.unix_events._UnixSelectorEventLoop
    ) -> None:
        # Validate connection string
        pattern = "([\\S]+):([\\S]+):([\\S]+)"
        match = re.match(pattern, instance_connection_string)

        if match:
            self.instance_connection_string = instance_connection_string
            self.project = match[1]
            self.instance = match[2]
        else:
            raise CloudSQLConnectionStringError(
                "Arg instance_connection_string must be in "
                + "format: project:region:instance."
            )

        #
        # set current to future InstanceMetadata
        # set next to the future future InstanceMetadata
