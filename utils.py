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

import pymysql.cursors
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import os

# Connect method used in the SQLAlchemy creator
def connect():
    return pymysql.connect(
        host=os.environ['db_host'],
        user=os.environ['db_user'],
        password=os.environ['db_pass'],
        db=os.environ['db_name'],
        ssl={
            'ssl': {
                'ca': './ca.pem',
                'cert': './cert.pem',
                'key': './priv.pem'
            }
        }
    )

