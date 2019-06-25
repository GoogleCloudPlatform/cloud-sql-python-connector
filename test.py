##############################################################################
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#############################################################################

import pytest  # noqa: F401; pylint: disable=unused-variable
from utils import generate_keys, write_to_file



def test_generate_keys_1():
    res1, res2 = generate_keys()
    assert (res1 is not None) and (res2 is not None)


def test_generate_keys_2():
    priv, pub = generate_keys()

    message_src = "According to all known laws of aviation, there is no way a bee should be able to fly."

    encrypted_msg = pub.encrypt(
        message_src,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    decrypted_msg = priv.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    assert decrypted_msg == message_src
