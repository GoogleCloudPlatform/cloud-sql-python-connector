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
import os
import threading

import asyncio
import pytest  # noqa F401 Needed to run the tests


@pytest.fixture
def async_loop():
    """
    Creates a loop in a background thread and returns it to use for testing.
    """
    loop = asyncio.new_event_loop()
    thr = threading.Thread(target=loop.run_forever)
    thr.start()
    yield loop
    loop.stop()
    thr.join()


@pytest.fixture
def connect_string():
    """
    Retrieves a valid connection string from the environment and
    returns it.
    """
    try:
        connect_string = os.environ["INSTANCE_CONNECTION_NAME"]
    except KeyError:
        raise KeyError(
            "Please set environment variable 'INSTANCE_CONNECTION"
            + "_NAME' to a valid Cloud SQL connection string."
        )

    return connect_string
