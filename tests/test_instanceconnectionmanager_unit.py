""""
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

import pytest

from google.cloud.sql.connector.InstanceConnectionManager import (
    InstanceConnectionManager,
    CloudSQLConnectionError,
)
import asyncio


def test_InstanceConnectionManager_connection_string():
    """
    Test to check whether the __init__() method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """
    loop = asyncio.new_event_loop()
    connect_string = "test-project:test-region:test-instance"
    icm = InstanceConnectionManager(connect_string, loop)
    assert (
        icm._project == "test-project"
        and icm._region == "test-region"
        and icm._instance == "test-instance"
    )


def test_InstanceConnectionManager_wrong_connection_string():
    """
    Test to check whether the __init__() method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """
    loop = asyncio.new_event_loop()
    with pytest.raises(CloudSQLConnectionError):
        InstanceConnectionManager("test-project:test-region", loop)
