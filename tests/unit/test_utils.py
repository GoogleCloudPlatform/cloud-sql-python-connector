"""
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
import threading

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from google.auth.credentials import AnonymousCredentials
import pytest

from google.cloud.sql.connector import Connector
from google.cloud.sql.connector import utils


@pytest.mark.asyncio
async def test_generate_keys_not_return_none() -> None:
    """
    Test to check if objects are being produced from the generate_keys()
    function.
    """

    res1, res2 = await utils.generate_keys()
    assert (res1 is not None) and (res2 is not None)


@pytest.mark.asyncio
async def test_generate_keys_returns_bytes_and_str() -> None:
    """
    Test to check if objects produced from the generate_keys() function are of
    the expected types.
    """

    res1, res2 = await utils.generate_keys()
    assert isinstance(res1, bytes) and (isinstance(res2, str))


@pytest.mark.asyncio
async def test_generate_keys_preserves_parameters_and_serialization() -> None:
    private_bytes, public_text = await utils.generate_keys()
    private = serialization.load_pem_private_key(private_bytes, password=None)
    public = serialization.load_pem_public_key(public_text.encode("UTF-8"))
    assert private.key_size == 2048
    assert private.public_key().public_numbers().e == 65537
    assert public.public_numbers() == private.public_key().public_numbers()
    assert private_bytes.startswith(b"-----BEGIN RSA PRIVATE KEY-----")
    assert public_text.startswith("-----BEGIN PUBLIC KEY-----")
    signature = private.sign(b"synthetic", padding.PKCS1v15(), hashes.SHA256())
    public.verify(signature, b"synthetic", padding.PKCS1v15(), hashes.SHA256())


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("fail", [False, True])
async def test_generate_keys_keeps_loop_live_and_drains_work(
    monkeypatch: pytest.MonkeyPatch, cancel: bool, fail: bool
) -> None:
    started, release = threading.Event(), threading.Event()
    loop_thread = threading.get_ident()
    events: list[str] = []

    def generate() -> tuple[bytes, str]:
        assert threading.get_ident() != loop_thread
        events.append("started")
        started.set()
        assert release.wait(10), "test did not release key generation"
        events.append("finished")
        if fail:
            raise RuntimeError("synthetic generation failure")
        return b"synthetic", "synthetic"

    monkeypatch.setattr(utils, "_generate_keys_sync", generate)
    task = asyncio.create_task(utils.generate_keys())
    try:
        assert await asyncio.wait_for(asyncio.to_thread(started.wait, 5), timeout=6)
        await asyncio.sleep(0)
        assert not task.done()
        if cancel:
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
            assert not task.done()
            assert events == ["started"]
    finally:
        release.set()
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
    elif fail:
        with pytest.raises(RuntimeError, match="synthetic generation failure"):
            await asyncio.wait_for(task, timeout=5)
    else:
        assert await asyncio.wait_for(task, timeout=5) == (b"synthetic", "synthetic")
    assert events == ["started", "finished"]


@pytest.mark.asyncio
async def test_connector_keeps_one_key_future_on_its_loop() -> None:
    loop = asyncio.get_running_loop()
    connector = Connector(loop=loop, credentials=AnonymousCredentials())
    try:
        assert connector._loop is loop
        assert connector._keys.get_loop() is loop
        first, second = await asyncio.gather(
            asyncio.shield(connector._keys), asyncio.shield(connector._keys)
        )
        assert first is second
        assert connector._thread is None
    finally:
        await connector.close_async()


def test_format_database_user_postgres() -> None:
    """
    Test that format_database_user properly formats Postgres IAM database users.
    """
    service_account = utils.format_database_user(
        "POSTGRES_14", "service-account@test.iam"
    )
    service_account2 = utils.format_database_user(
        "POSTGRES_14", "service-account@test.iam.gserviceaccount.com"
    )
    assert service_account == "service-account@test.iam"
    assert service_account2 == "service-account@test.iam"
    user = utils.format_database_user("POSTGRES_14", "test@test.com")
    assert user == "test@test.com"


def test_format_database_user_mysql() -> None:
    """
    Test that format_database _user properly formats MySQL IAM database users.
    """
    service_account = utils.format_database_user(
        "MYSQL_8_0", "service-account@test.iam"
    )
    service_account2 = utils.format_database_user(
        "MYSQL_8_0", "service-account@test.iam.gserviceaccount.com"
    )
    service_account3 = utils.format_database_user("MYSQL_8_0", "service-account")
    assert service_account == "service-account"
    assert service_account2 == "service-account"
    assert service_account3 == "service-account"
    user = utils.format_database_user("MYSQL_8_0", "test@test.com")
    user2 = utils.format_database_user("MYSQL_8_0", "test")
    assert user == "test"
    assert user2 == "test"
