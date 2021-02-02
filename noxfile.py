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
import shutil
import sys
import nox

BLACK_PATHS = ["google", "tests"]

if os.path.exists("samples"):
    BLACK_PATHS.append("samples")


@nox.session(python="3.7")
def lint(session):
    """Run linters.
    Returns a failure if the linters find linting errors or sufficiently
    serious code quality issues.
    """
    session.install("flake8", "black")
    session.install("-r", "requirements.txt")
    session.run("black", "--check", *BLACK_PATHS)
    session.run("flake8", "google", "tests")


@nox.session(python="3.6")
def blacken(session):
    """Run black.
    Format code to uniform standard.
    This currently uses Python 3.6 due to the automated Kokoro run of synthtool.
    That run uses an image that doesn't have 3.6 installed. Before updating this
    check the state of the `gcp_ubuntu_config` we use for that Kokoro run.
    """
    session.install("black")
    session.run("black", *BLACK_PATHS)


def default(session, path):
    # Install all test dependencies, then install this package in-place.
    session.install("-r", "requirements-test.txt")
    session.install("-e", ".")
    session.install("-r", "requirements.txt")
    # Run py.test against the unit tests.
    session.run(
        "py.test",
        # "--cov=util",
        # "--cov=connector",
        "--cov-append",
        "--cov-config=.coveragerc",
        "--cov-report=",
        "--cov-fail-under=0",
        path,
        *session.posargs,
    )


@nox.session(python=["3.6", "3.7", "3.8", "3.9"])
def unit(session):
    default(session, os.path.join("tests", "unit"))

@nox.session(python=["3.6", "3.7", "3.8", "3.9"])
def system(session):
    default(session, os.path.join("tests", "system"))

@nox.session(python=["3.6", "3.7", "3.8", "3.9"])
def test(session):
    default(session, os.path.join("tests", "unit"))
    default(session, os.path.join("tests", "system"))

# @nox.session(python="3.7")
# def cover(session):
# """Run the final coverage report.
# This outputs the coverage report aggregating coverage from the unit
# test runs (not system test runs), and then erases coverage data.
# """
# session.install("coverage", "pytest-cov")
# session.run("coverage", "report", "--show-missing", "--fail-under=100")

# session.run("coverage", "erase")
