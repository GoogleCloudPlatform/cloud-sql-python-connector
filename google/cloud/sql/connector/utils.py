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
from functools import partial, wraps

import pymysql.cursors
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def run_function_as_async(func):
    @wraps(func)
    async def wrapped_sync_function(*args, **kwargs):
        partial_func = partial(func, *args, **kwargs)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial_func)

    return wrapped_sync_function

def connect(host, user, password, db_name):
    """
    Connect method to be used as a custom creator in the SQLAlchemy engine
    creation.
    """
    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        db=db_name,
        ssl={
            "ssl": {
                "ca": "./ca.pem",
                "cert": "./cert.pem",
                "key": "./priv.pem",
            }  # noqa: E501
        },
    )


@run_function_as_async
def generate_private_key_object():
    return rsa.generate_private_key(
        backend=default_backend(), public_exponent=65537, key_size=2048
    )

@run_function_as_async
def get_private_key_bytes(private_key_obj):
    return private_key_obj.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

@run_function_as_async
def get_public_key_bytes(private_key_obj):
    return private_key_obj.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


async def generate_keys():
    """
    A helper function to generate the private and public keys.

    backend - The value specified is default_backend(). This is because the
    cryptography library used to support different backends, but now only uses
    the default_backend().

    public_exponent - The public exponent is one of the variables used in the
    generation of the keys. 65537 is recommended due to being a good balance
    between speed and security.

    key_size - The cryptography documentation recommended a key_size
    of at least 2048.
    """
    private_key_obj = await generate_private_key_object()
    
    return await asyncio.gather(
        get_private_key_bytes(private_key_obj),
        get_public_key_bytes(private_key_obj)
    )


def write_to_file(serverCaCert, ephemeralCert, priv_key):
    """
    Helper function to write the serverCaCert, ephemeral certificate and
    private key to .pem files
    """
    with open("keys/ca.pem", "w+") as ca_out:
        ca_out.write(serverCaCert)
    with open("keys/cert.pem", "w+") as ephemeral_out:
        ephemeral_out.write(ephemeralCert)
    with open("keys/priv.pem", "wb") as priv_out:
        priv_out.write(priv_key)
