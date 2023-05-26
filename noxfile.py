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


from __future__ import absolute_import
import os
import nox

BLACK_PATHS = ["google", "tests"]

if os.path.exists("samples"):
    BLACK_PATHS.append("samples")


@nox.session
def lint(session):
    """Run linters.
    Returns a failure if the linters find linting errors or sufficiently
    serious code quality issues.
    """
    session.install("-r", "requirements-test.txt")
    session.install("-r", "requirements.txt")
    session.install("flake8-import-order")
    session.run("black", "--check", *BLACK_PATHS)
    session.run(
        "flake8",
        "--import-order-style=google",
        "--application-import-names=google,tests",
        "google",
        "tests",
    )
    session.run("mypy", "google", "tests")
    session.run("python", "setup.py", "sdist")
    session.run("twine", "check", "dist/*")


def default(session, path):
    # Install all test dependencies, then install this package in-place.
    session.install("-r", "requirements-test.txt")
    session.install("-e", ".")
    session.install("-r", "requirements.txt")
    # Run py.test against the unit tests.
    session.run(
        "pytest",
        "--cov=google/cloud/sql/connector",
        "-v",
        "--cov-config=.coveragerc",
        "--cov-report=",
        "--cov-fail-under=0",
        "--junitxml=sponge_log.xml",
        path,
        *session.posargs,
    )


@nox.session(python=["3.7", "3.8", "3.9", "3.10", "3.11"])
def unit(session):
    default(session, os.path.join("tests", "unit"))


@nox.session(python=["3.7", "3.8", "3.9", "3.10", "3.11"])
def system(session):
    default(session, os.path.join("tests", "system"))


@nox.session(python=["3.7", "3.8", "3.9", "3.10", "3.11"])
def test(session):
    default(session, os.path.join("tests", "unit"))
    default(session, os.path.join("tests", "system"))
