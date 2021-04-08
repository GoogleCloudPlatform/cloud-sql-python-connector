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

import asyncio
import pytest  # noqa F401 Needed to run the tests
from google.cloud.sql.connector.instance_connection_manager import (
    InstanceConnectionManager,
)
from google.cloud.sql.connector.utils import generate_keys

@pytest.fixture
def icm(async_loop: asyncio.AbstractEventLoop, connect_string: str) -> None:
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)
    yield icm

def test_InstanceConnectionManager_init(async_loop):
    """
    Test to check whether the __init__ method of InstanceConnectionManager
    can tell if the connection string that's passed in is formatted correctly.
    """

    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)
    icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)
    project_result = icm._project
    region_result = icm._region
    instance_result = icm._instance

    del icm

    assert (
        project_result == "test-project"
        and region_result == "test-region"
        and instance_result == "test-instance"
    )


@pytest.mark.asyncio
async def test_InstanceConnectionManager_perform_refresh(icm):
    """
    Test to check whether _get_perform works as described given valid
    conditions.
    """
    task = await icm._perform_refresh()

    assert isinstance(task, asyncio.Task)

    del icm
