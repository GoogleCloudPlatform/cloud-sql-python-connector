""""
Copyright 2021 Google LLC

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

import pytest  # noqa F401 Needed to run the tests
from google.cloud.sql.connector.instance_connection_manager import (
    InstanceConnectionManager,
)
from google.cloud.sql.connector import connector
from google.cloud.sql.connector.utils import generate_keys
import asyncio
from unittest.mock import patch


def test_connect_timeout(connect_string, async_loop):
    timeout = 10

    async def timeout_stub(*args, **kwargs):
        await asyncio.sleep(timeout + 10)

    keys = asyncio.run_coroutine_threadsafe(generate_keys(), async_loop)

    icm = InstanceConnectionManager(connect_string, "pymysql", keys, async_loop)
    icm._connect = timeout_stub

    mock_instances = {}
    mock_instances[connect_string] = icm
    with patch.dict(connector._instances, mock_instances):
        pytest.raises(
            TimeoutError, connector.connect, connect_string, "pymysql", timeout=timeout
        )

    del icm