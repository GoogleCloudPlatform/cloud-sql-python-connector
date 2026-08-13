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
from unittest.mock import AsyncMock
from unittest.mock import patch

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


@pytest.mark.asyncio
async def test_asyncpg_import_error(kwargs: Any) -> None:
    """Test to verify that connect raises ImportError if asyncpg is not installed."""
    with patch.dict("sys.modules", {"asyncpg": None}):
        with pytest.raises(ImportError) as excinfo:
            await connect("0.0.0.0", ssl.create_default_context(), **kwargs)
        assert 'Unable to import module "asyncpg."' in str(excinfo.value)


@pytest.mark.asyncio
async def test_asyncpg_database_param(kwargs: Any) -> None:
    """Test that asyncpg wrapper accepts both 'db' and 'database'."""
    ip_addr = "0.0.0.0"
    context = ssl.create_default_context()

    # Test with 'db'
    kwargs_db = kwargs.copy()
    kwargs_db["db"] = "my-db-1"
    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
        await connect(ip_addr, context, **kwargs_db)
        mock_connect.assert_called_once_with(
            user=kwargs["user"],
            database="my-db-1",
            password=kwargs.get("password"),
            host=ip_addr,
            port=3307,
            ssl=context,
            direct_tls=True,
        )

    # Test with 'database'
    kwargs_database = kwargs.copy()
    kwargs_database["database"] = "my-db-2"
    if "db" in kwargs_database:
        del kwargs_database["db"]
    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
        await connect(ip_addr, context, **kwargs_database)
        mock_connect.assert_called_once_with(
            user=kwargs["user"],
            database="my-db-2",
            password=kwargs.get("password"),
            host=ip_addr,
            port=3307,
            ssl=context,
            direct_tls=True,
        )


@pytest.mark.asyncio
async def test_asyncpg_database_missing(kwargs: Any) -> None:
    """Test that asyncpg wrapper raises KeyError if database is missing."""
    if "db" in kwargs:
        del kwargs["db"]
    if "database" in kwargs:
        del kwargs["database"]
    with pytest.raises(KeyError, match="database"):
        await connect("0.0.0.0", ssl.create_default_context(), **kwargs)


