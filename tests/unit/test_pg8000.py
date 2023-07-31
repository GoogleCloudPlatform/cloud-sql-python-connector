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
from functools import partial
from typing import Any

from mock import patch
from mocks import create_ssl_context
import pytest

from google.cloud.sql.connector.pg8000 import connect


@pytest.mark.usefixtures("server")
@pytest.mark.asyncio
async def test_pg8000(kwargs: Any) -> None:
    """Test to verify that pg8000 gets to proper connection call."""
    ip_addr = "127.0.0.1"
    # build ssl.SSLContext
    context = await create_ssl_context()
    # force all wrap_socket calls to have do_handshake_on_connect=False
    setattr(
        context,
        "wrap_socket",
        partial(context.wrap_socket, do_handshake_on_connect=False),
    )
    with patch("pg8000.dbapi.connect") as mock_connect:
        mock_connect.return_value = True
        connection = connect(ip_addr, context, **kwargs)
        assert connection is True
        # verify that driver connection call would be made
        assert mock_connect.assert_called_once
