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
import datetime
from google.cloud.sql.connector.rate_limiter import AsyncRateLimiter
from google.auth.credentials import Credentials
from google.cloud.sql.connector.instance import (
    IPTypes,
    Instance,
    InstanceMetadata,
)
from google.cloud.sql.connector.exceptions import (
    AutoIAMAuthNotSupported,
    CloudSQLIPTypeError,
    CredentialsTypeError,
)
from google.cloud.sql.connector.utils import generate_keys
from mock import patch
from aioresponses import aioresponses
from aiohttp import ClientResponseError, RequestInfo

# import mocks
import mocks


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
    keys = asyncio.wrap_future(
        asyncio.run_coroutine_threadsafe(generate_keys(), event_loop), loop=event_loop
    )
    with patch("google.cloud.sql.connector.utils.default") as mock_auth:
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
    keys = asyncio.wrap_future(
        asyncio.run_coroutine_threadsafe(generate_keys(), event_loop), loop=event_loop
    )
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
    setattr(instance, "_perform_refresh", mocks.instance_metadata_success)

    old_metadata = await instance._current

    # schedule refresh immediately and await it
    refresh_task = instance._schedule_refresh(0)
    refresh_metadata = await refresh_task

    # check that current metadata has been replaced with refresh metadata
    assert instance._current.result() == refresh_metadata
    assert old_metadata != instance._current.result()
    assert isinstance(instance._current.result(), mocks.MockMetadata)
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
    setattr(instance, "_perform_refresh", mocks.instance_metadata_error)

    # schedule refresh immediately
    refresh_task = instance._schedule_refresh(0)

    # wait for invalid refresh to finish
    with pytest.raises(mocks.BadRefresh):
        assert await refresh_task

    # check that invalid refresh did not replace valid current metadata
    assert instance._current == old_task
    assert isinstance(await instance._current, InstanceMetadata)


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
    setattr(instance, "_perform_refresh", mocks.instance_metadata_error)

    # set current to invalid data (error)
    instance._current = instance._schedule_refresh(0)

    # check that current is now invalid (error)
    with pytest.raises(mocks.BadRefresh):
        assert await instance._current

    # stub _perform_refresh to return a valid MockMetadata instance
    setattr(instance, "_perform_refresh", mocks.instance_metadata_success)

    # schedule refresh immediately and await it
    refresh_task = instance._schedule_refresh(0)
    refresh_metadata = await refresh_task

    # check that current is now valid MockMetadata
    assert instance._current.result() == refresh_metadata
    assert isinstance(instance._current.result(), mocks.MockMetadata)
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
    # make sure initial refresh is finished
    await instance._current
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
    assert isinstance(await instance._current, InstanceMetadata)


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
async def test_perform_refresh(
    instance: Instance,
    mock_instance: mocks.FakeCSQLInstance,
) -> None:
    """
    Test that _perform_refresh returns valid InstanceMetadata object.
    """
    instance_metadata = await instance._perform_refresh()

    # verify instance metadata object is returned
    assert isinstance(instance_metadata, InstanceMetadata)
    # verify instance metadata expiration
    assert (
        mock_instance.cert._not_valid_after.replace(microsecond=0)  # type: ignore
        == instance_metadata.expiration
    )


@pytest.mark.asyncio
async def test_perform_refresh_expiration(
    instance: Instance,
) -> None:
    """
    Test that _perform_refresh returns InstanceMetadata with proper expiration.

    If credentials expiration is less than cert expiration,
    credentials expiration should be used.
    """
    # set credentials expiration to 1 minute from now
    expiration = datetime.datetime.utcnow() + datetime.timedelta(minutes=1)
    setattr(instance._credentials, "expiry", expiration)
    setattr(instance, "_enable_iam_auth", True)
    # set all credentials to valid so downscoped credential does not refresh
    with patch.object(Credentials, "valid", True):
        instance_metadata = await instance._perform_refresh()

    # verify instance metadata object is returned
    assert isinstance(instance_metadata, InstanceMetadata)
    # verify instance metadata uses credentials expiration
    assert expiration == instance_metadata.expiration


@pytest.mark.asyncio
async def test_connect_info(
    instance: Instance,
) -> None:
    """
    Test that connect_info returns current metadata and preferred IP.
    """
    instance_metadata, ip_addr = await instance.connect_info(IPTypes.PUBLIC)

    # verify metadata and ip address
    assert isinstance(instance_metadata, InstanceMetadata)
    assert ip_addr == "0.0.0.0"
    # cleanup instance
    await instance.close()


@pytest.mark.asyncio
async def test_get_preferred_ip(instance: Instance) -> None:
    """
    Test that get_preferred_ip returns proper IP address
    for both Public and Private IP addresses.
    """
    instance_metadata: InstanceMetadata = await instance._current

    # test public IP as preferred IP for connection
    ip_addr = instance_metadata.get_preferred_ip(IPTypes.PUBLIC)
    # verify public ip address is preferred
    assert ip_addr == "0.0.0.0"

    # test private IP as preferred IP for connection
    ip_addr = instance_metadata.get_preferred_ip(IPTypes.PRIVATE)
    # verify private ip address is preferred
    assert ip_addr == "1.1.1.1"


@pytest.mark.asyncio
async def test_get_preferred_ip_CloudSQLIPTypeError(instance: Instance) -> None:
    """
    Test that get_preferred_ip throws proper CloudSQLIPTypeError
    when missing Public or Private IP addresses.
    """
    instance_metadata: InstanceMetadata = await instance._current
    instance_metadata.ip_addrs = {"PRIVATE": "1.1.1.1"}
    # test error when Public IP is missing
    with pytest.raises(CloudSQLIPTypeError):
        instance_metadata.get_preferred_ip(IPTypes.PUBLIC)

    # test error when Private IP is missing
    instance_metadata.ip_addrs = {"PRIMARY": "0.0.0.0"}
    with pytest.raises(CloudSQLIPTypeError):
        instance_metadata.get_preferred_ip(IPTypes.PRIVATE)


@pytest.mark.asyncio
async def test_ClientResponseError(
    fake_credentials: Credentials, event_loop: asyncio.AbstractEventLoop
) -> None:
    """
    Test that detailed error message is applied to ClientResponseError.
    """
    # mock Cloud SQL Admin API calls with exceptions
    keys = asyncio.wrap_future(
        asyncio.run_coroutine_threadsafe(generate_keys(), event_loop), loop=event_loop
    )
    get_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance/connectSettings"
    post_url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-project/instances/my-instance:generateEphemeralCert"
    with aioresponses() as mocked:
        mocked.get(
            get_url,
            status=403,
            exception=ClientResponseError(
                RequestInfo(get_url, "GET", headers=[]), history=[], status=403  # type: ignore
            ),
            repeat=True,
        )
        mocked.post(
            post_url,
            status=403,
            exception=ClientResponseError(
                RequestInfo(post_url, "POST", headers=[]), history=[], status=403  # type: ignore
            ),
            repeat=True,
        )
        # verify that error is raised with detailed error message
        try:
            instance = Instance(
                "my-project:my-region:my-instance",
                "pymysql",
                keys,
                event_loop,
                credentials=fake_credentials,
            )
            await instance._current
        except ClientResponseError as e:
            assert e.status == 403
            assert (
                e.message == "Forbidden: Authenticated IAM principal does not "
                "seeem authorized to make API request. Verify "
                "'Cloud SQL Admin API' is enabled within your GCP project and "
                "'Cloud SQL Client' role has been granted to IAM principal."
            )
        finally:
            await instance.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mock_instance",
    [
        mocks.FakeCSQLInstance(db_version="SQLSERVER_2019_STANDARD"),
    ],
)
async def test_AutoIAMAuthNotSupportedError(instance: Instance) -> None:
    """
    Test that AutoIAMAuthNotSupported exception is raised
    for SQL Server and MySQL instances.
    """
    instance._enable_iam_auth = True
    with pytest.raises(AutoIAMAuthNotSupported):
        await instance._current
