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
from unittest.mock import patch
import datetime
from typing import Dict
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
import pytest  # noqa F401 Needed to run the tests
from google.auth.credentials import Credentials
from google.cloud.sql.connector.instance import (
    Instance,
    CredentialsTypeError,
    InstanceMetadata,
)
from google.cloud.sql.connector.utils import generate_keys

# import mocks
from mocks import (
    generate_cert,
    self_signed_cert,
    client_key_signed_cert,
    get_keys,
    BadRefresh,
    instance_metadata_error,
    instance_metadata_success,
    MockMetadata,
    mock_get_ephemeral,
    mock_get_metadata,
)


@pytest.fixture
def instance(
    fake_credentials: Credentials,
    event_loop: asyncio.AbstractEventLoop,
) -> Instance:
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        keys = asyncio.run_coroutine_threadsafe(generate_keys(), event_loop)
        instance = Instance(
            "my-project:my-region:my-instance", "pymysql", keys, event_loop
        )
        # stub _perform_refresh to return a "valid" MockMetadata object
        setattr(instance, "_perform_refresh", instance_metadata_success)
        instance._current = instance._schedule_refresh(0)
    return instance


@pytest.fixture
def test_rate_limiter(event_loop: asyncio.AbstractEventLoop) -> AsyncRateLimiter:
    return AsyncRateLimiter(max_capacity=1, rate=1 / 2, loop=event_loop)


@pytest.mark.asyncio
async def test_Instance_init(
    fake_credentials: Credentials, event_loop: asyncio.AbstractEventLoop
) -> None:
    """
    Test to check whether the __init__ method of Instance
    can tell if the connection string that's passed in is formatted correctly.
    """

    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), event_loop)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        instance = Instance(connect_string, "pymysql", keys, event_loop)
    project_result = instance._project
    region_result = instance._region
    instance_result = instance._instance
    assert (
        project_result == "test-project"
        and region_result == "test-region"
        and instance_result == "test-instance"
    )
    # cleanup instance
    await instance.close()


@pytest.mark.asyncio
async def test_Instance_init_bad_credentials(
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    """
    Test to check whether the __init__ method of Instance
    throws proper error for bad credentials arg type.
    """
    connect_string = "test-project:test-region:test-instance"
    keys = asyncio.run_coroutine_threadsafe(generate_keys(), event_loop)
    with pytest.raises(CredentialsTypeError):
        instance = Instance(connect_string, "pymysql", keys, event_loop, credentials=1)
        await instance.close()


@pytest.mark.asyncio
async def test_schedule_refresh_replaces_result(
    instance: Instance, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _schedule_refresh replaces a valid result with another valid result
    """
    # allow more frequent refreshes for tests
    setattr(instance, "_refresh_rate_limiter", test_rate_limiter)

    # stub _perform_refresh to return a "valid" MockMetadata object
    setattr(instance, "_perform_refresh", instance_metadata_success)

    old_metadata = await instance._current

    # schedule refresh immediately and await it
    refresh_task = instance._schedule_refresh(0)
    refresh_metadata = await refresh_task

    # check that current metadata has been replaced with refresh metadata
    assert instance._current.result() == refresh_metadata
    assert old_metadata != instance._current.result()
    assert isinstance(instance._current.result(), MockMetadata)
    # cleanup instance
    await instance.close()


@pytest.mark.asyncio
async def test_schedule_refresh_wont_replace_valid_result_with_invalid(
    instance: Instance, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh won't replace a valid _current
    value with an invalid one
    """
    # allow more frequent refreshes for tests
    setattr(instance, "_refresh_rate_limiter", test_rate_limiter)

    await instance._current
    old_task = instance._current

    # stub _perform_refresh to throw an error
    setattr(instance, "_perform_refresh", instance_metadata_error)

    # schedule refresh immediately
    refresh_task = instance._schedule_refresh(0)

    # wait for invalid refresh to finish
    with pytest.raises(BadRefresh):
        assert await refresh_task

    # check that invalid refresh did not replace valid current metadata
    assert instance._current == old_task
    assert isinstance(instance._current.result(), MockMetadata)
    await instance.close()


@pytest.mark.asyncio
async def test_schedule_refresh_replaces_invalid_result(
    instance: Instance, test_rate_limiter: AsyncRateLimiter
) -> None:
    """
    Test to check whether _perform_refresh will replace an invalid refresh result with
    a valid one
    """
    # allow more frequent refreshes for tests
    setattr(instance, "_refresh_rate_limiter", test_rate_limiter)

    # stub _perform_refresh to throw an error
    setattr(instance, "_perform_refresh", instance_metadata_error)

    # set current to invalid data (error)
    instance._current = instance._schedule_refresh(0)

    # check that current is now invalid (error)
    with pytest.raises(BadRefresh):
        assert await instance._current

    # stub _perform_refresh to return a valid MockMetadata instance
    setattr(instance, "_perform_refresh", instance_metadata_success)

    # schedule refresh immediately and await it
    refresh_task = instance._schedule_refresh(0)
    refresh_metadata = await refresh_task

    # check that current is now valid MockMetadata
    assert instance._current.result() == refresh_metadata
    assert isinstance(instance._current.result(), MockMetadata)
    await instance.close()


@pytest.mark.asyncio
async def test_force_refresh_cancels_pending_refresh(
    instance: Instance,
    test_rate_limiter: AsyncRateLimiter,
) -> None:
    """
    Test that force_refresh cancels pending task if refresh_in_progress event is not set.
    """
    # allow more frequent refreshes for tests
    setattr(instance, "_refresh_rate_limiter", test_rate_limiter)

    # since the pending refresh isn't for another 55 min, the refresh_in_progress event
    # shouldn't be set
    pending_refresh = instance._next

    assert instance._refresh_in_progress.is_set() is False

    instance.force_refresh()

    # pending_refresh has to be awaited for it to raised as cancelled
    with pytest.raises(asyncio.CancelledError):
        assert await pending_refresh

    # verify pending_refresh has now been cancelled
    assert pending_refresh.cancelled() is True
    assert isinstance(instance._current.result(), MockMetadata)
    await instance.close()


@pytest.mark.asyncio
async def test_auth_init_with_credentials_object(
    instance: Instance, fake_credentials: Credentials
) -> None:
    """
    Test that Instance's _auth_init initializes _credentials
    when passed a google.auth.credentials.Credentials object.
    """
    setattr(instance, "_credentials", None)
    with patch(
        "google.cloud.sql.connector.instance.with_scopes_if_required"
    ) as mock_auth:
        mock_auth.return_value = fake_credentials
        instance._auth_init(credentials=fake_credentials)
        assert isinstance(instance._credentials, Credentials)
        mock_auth.assert_called_once()
    await instance.close()


@pytest.mark.asyncio
async def test_auth_init_with_default_credentials(
    instance: Instance, fake_credentials: Credentials
) -> None:
    """
    Test that Instance's _auth_init initializes _credentials
    with application default credentials when credentials are not specified.
    """
    setattr(instance, "_credentials", None)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        instance._auth_init(credentials=None)
        assert isinstance(instance._credentials, Credentials)
        mock_auth.assert_called_once()
    await instance.close()


@pytest.mark.asyncio
async def test_Instance_close(instance: Instance) -> None:
    """
    Test that Instance's close method
    cancels tasks and closes ClientSession.
    """
    # make sure current metadata task is done
    await instance._current
    assert instance._current.cancelled() is False
    assert instance._next.cancelled() is False
    assert instance._client_session.closed is False
    # run close() to cancel tasks and close ClientSession
    await instance.close()
    # verify tasks are cancelled and ClientSession is closed
    assert (instance._current.done() or instance._current.cancelled()) is True
    assert instance._next.cancelled() is True
    assert instance._client_session.closed is True


@pytest.mark.asyncio
@patch("google.cloud.sql.connector.instance._get_ephemeral")
@patch("google.cloud.sql.connector.instance._get_metadata")
async def test_perform_refresh(
    mock_metadata: Dict,
    mock_ephemeral: str,
    fake_credentials: Credentials,
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    """
    Test that _perform_refresh returns valid InstanceMetadata object.
    """
    # generate keys and certs for test
    cert, priv_key = generate_cert("my-project", "my-instance")
    server_ca_cert = self_signed_cert(cert, priv_key)
    keys = asyncio.create_task(get_keys())
    _, client_key = await keys
    ephemeral_cert = client_key_signed_cert(cert, priv_key, client_key)

    # mock instance metadata and ephemeral cert
    mock_metadata.return_value = await mock_get_metadata(server_ca_cert)
    mock_ephemeral.return_value = await mock_get_ephemeral(ephemeral_cert)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        instance = Instance(
            "my-project:my-region:my-instance", "pymysql", keys, event_loop
        )
    instance_metadata = await instance._perform_refresh()

    # verify instance metadata object is returned
    assert isinstance(instance_metadata, InstanceMetadata)
    # verify instance metadata expiration
    assert cert._not_valid_after.replace(microsecond=0) == instance_metadata.expiration


@pytest.mark.asyncio
@patch("google.cloud.sql.connector.instance._get_ephemeral")
@patch("google.cloud.sql.connector.instance._get_metadata")
async def test_perform_refresh_expiration(
    mock_metadata: Dict,
    mock_ephemeral: str,
    fake_credentials: Credentials,
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    """
    Test that _perform_refresh returns InstanceMetadata with proper expiration.

    If credentials expiration is less than cert expiration,
    credentials expiration should be used.
    """
    # generate keys and certs for test
    cert, priv_key = generate_cert("my-project", "my-instance")
    server_ca_cert = self_signed_cert(cert, priv_key)
    keys = asyncio.create_task(get_keys())
    _, client_key = await keys
    ephemeral_cert = client_key_signed_cert(cert, priv_key, client_key)

    # mock instance metadata and ephemeral cert
    mock_metadata.return_value = await mock_get_metadata(server_ca_cert)
    mock_ephemeral.return_value = await mock_get_ephemeral(ephemeral_cert)
    with patch("google.auth.default") as mock_auth:
        mock_auth.return_value = fake_credentials, None
        instance = Instance(
            "my-project:my-region:my-instance",
            "pymysql",
            keys,
            event_loop,
            enable_iam_auth=True,
        )
    # set credentials expiration to 1 minute from now
    expiration = datetime.datetime.utcnow() + datetime.timedelta(minutes=1)
    setattr(instance._credentials, "expiry", expiration)
    instance_metadata = await instance._perform_refresh()

    # verify instance metadata object is returned
    assert isinstance(instance_metadata, InstanceMetadata)
    # verify instance metadata uses credentials expiration
    assert expiration == instance_metadata.expiration
