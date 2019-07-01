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

from google.cloud.sql.connector import utils


def test_generate_keys_not_return_none():
    """
    Test to check if objects are being produced from the generate_keys()
    function.
    """

    res1, res2 = utils.generate_keys()
    assert (res1 is not None) and (res2 is not None)


def test_generate_keys_returns_bytes():
    """
    Test to check if objects produced from the generate_keys() function are of
    type bytes.
    """

    res1, res2 = utils.generate_keys()
    assert isinstance(res1, bytes) and (isinstance(res2, bytes))
