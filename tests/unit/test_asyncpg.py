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
import ssl
from typing import Any

from mock import AsyncMock
from mock import patch
import pytest

from google.cloud.sql.connector.asyncpg import connect


@pytest.mark.asyncio
@patch("asyncpg.connect", new_callable=AsyncMock)
async def test_asyncpg(mock_connect: AsyncMock, kwargs: Any) -> None:
    """Test to verify that asyncpg gets to proper connection call."""
    ip_addr = "0.0.0.0"
    context = ssl.create_default_context()
    mock_connect.return_value = True
    connection = await connect(ip_addr, context, **kwargs)
    assert connection is True
    # verify that driver connection call would be made
    assert mock_connect.assert_called_once
