# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from setuptools import setup, find_packages



# Determine which namespaces are needed.
namespaces = ["google"]

packages = [
    package for package in find_packages() if package.startswith("google")
]

if "google.cloud" in packages:
    namespaces.append("google.cloud")

name = "cloud-sql-python-connector"
description = ""
version = ""
release_status = 'Development Status :: 3 - Alpha'
dependencies = [
    "aiohttp",
    "cryptography",
    "PyMySQL",
    "pytest",
    "Requests",
    "google-api-python-client"
]

setup(name="cloud-sql-python-connector", version=version, packages=find_packages())
