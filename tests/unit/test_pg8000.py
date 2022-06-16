"""
Copyright 2022 Google LLC

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
from unittest.mock import patch
import ssl
from typing import Any

from google.cloud.sql.connector.pg8000 import connect


def test_pg8000(kwargs: Any) -> None:
    """Test to verify that pg8000 gets to proper connection call."""
    ip_addr = "0.0.0.0"
    context = ssl.create_default_context()
    with patch("pg8000.dbapi.connect") as mock_connect:
        mock_connect.return_value = True
        connection = connect(ip_addr, context, **kwargs)
        assert connection is True
        # verify ssl.SSLContext has 'request_ssl' attribute set to false
        assert context.request_ssl is False  # type: ignore
        # verify that driver connection call would be made
        assert mock_connect.assert_called_once
