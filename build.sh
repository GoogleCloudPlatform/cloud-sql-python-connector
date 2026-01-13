#!/usr/bin/env bash

# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http=//www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Set SCRIPT_DIR to the current directory of this file.
SCRIPT_DIR=$(cd -P "$(dirname "$0")" >/dev/null 2>&1 && pwd)
SCRIPT_FILE="${SCRIPT_DIR}/$(basename "$0")"

##
## Local Development
##
## These functions should be used to run the local development process
##

if [[ ! -d venv ]] ; then
  echo "./venv not found. Setting up venv"
  python3 -m venv "$PWD/venv"
fi

source "$PWD/venv/bin/activate"

if which pip3 ; then
  PIP_CMD=pip3
elif which pip ; then
  PIP_CMD=pip
else
  echo "pip not found. Please add pip to your path."
  exit 1
fi
if ! which nox ; then
  python3 -m pip install nox
fi



## clean - Cleans the build output
function clean() {
  if [[ -d '.tools' ]] ; then
    rm -rf .tools
  fi
}

## build - Builds the project without running tests.
function build() {
  nox --sessions build
}

## test - Runs local unit tests.
function test() {
  nox --sessions unit --python=3.13
}

## e2e - Runs end-to-end integration tests.
function e2e() {
  if [[ ! -f .envrc ]] ; then
    write_e2e_env .envrc
  fi
  source .envrc
  nox --sessions system  --python=3.13
}

## fix - Fixes code format.
function fix() {
  nox --sessions format
}

## lint - runs the linters
function lint() {
  # Check the commit includes a go.mod that is fully
  # up to date.
  nox --sessions lint
}

## deps - updates project dependencies to latest
function deps() {
  if ! which pip-review ; then 
    python3 -m pip install pip-review
  fi
  pip-review --auto -r requirements.txt
  pip-review --auto -r requirements-test.txt
  echo "Dependencies updated successfully."
}

# write_e2e_env - Loads secrets from the gcloud project and writes
#     them to target/e2e.env to run e2e tests.
function write_e2e_env(){
  # All secrets used by the e2e tests in the form <env_name>=<secret_name>
  secret_vars=(
    MYSQL_CONNECTION_NAME=MYSQL_CONNECTION_NAME
    MYSQL_USER=MYSQL_USER
    MYSQL_USER_IAM=MYSQL_USER_IAM_GO
    MYSQL_PASS=MYSQL_PASS
    MYSQL_DB=MYSQL_DB
    MYSQL_MCP_CONNECTION_NAME=MYSQL_MCP_CONNECTION_NAME
    MYSQL_MCP_PASS=MYSQL_MCP_PASS
    POSTGRES_CONNECTION_NAME=POSTGRES_CONNECTION_NAME
    POSTGRES_USER=POSTGRES_USER
    POSTGRES_USER_IAM=POSTGRES_USER_IAM_GO
    POSTGRES_PASS=POSTGRES_PASS
    POSTGRES_DB=POSTGRES_DB
    POSTGRES_CAS_CONNECTION_NAME=POSTGRES_CAS_CONNECTION_NAME
    POSTGRES_CAS_PASS=POSTGRES_CAS_PASS
    POSTGRES_CUSTOMER_CAS_CONNECTION_NAME=POSTGRES_CUSTOMER_CAS_CONNECTION_NAME
    POSTGRES_CUSTOMER_CAS_PASS=POSTGRES_CUSTOMER_CAS_PASS
    POSTGRES_CUSTOMER_CAS_DOMAIN_NAME=POSTGRES_CUSTOMER_CAS_DOMAIN_NAME
    POSTGRES_CUSTOMER_CAS_INVALID_DOMAIN_NAME=POSTGRES_CUSTOMER_CAS_INVALID_DOMAIN_NAME
    POSTGRES_MCP_CONNECTION_NAME=POSTGRES_MCP_CONNECTION_NAME
    POSTGRES_MCP_PASS=POSTGRES_MCP_PASS
    SQLSERVER_CONNECTION_NAME=SQLSERVER_CONNECTION_NAME
    SQLSERVER_USER=SQLSERVER_USER
    SQLSERVER_PASS=SQLSERVER_PASS
    SQLSERVER_DB=SQLSERVER_DB
    QUOTA_PROJECT=QUOTA_PROJECT
  )

  if [[ -z "$TEST_PROJECT" ]] ; then
    echo "Set TEST_PROJECT environment variable to the project containing"
    echo "the e2e test suite secrets."
    exit 1
  fi

  echo "Getting test secrets from $TEST_PROJECT into $1"
  {
  for env_name in "${secret_vars[@]}" ; do
    env_var_name="${env_name%%=*}"
    secret_name="${env_name##*=}"
    set -x
    val=$(gcloud secrets versions access latest --project "$TEST_PROJECT" --secret="$secret_name")
    echo "export $env_var_name='$val'"
  done
  # Aliases for python e2e tests
  echo "export POSTGRES_CUSTOMER_CAS_PASS_VALID_DOMAIN_NAME=\"\$POSTGRES_CUSTOMER_CAS_DOMAIN_NAME\""
  echo "export POSTGRES_IAM_USER=\"\$POSTGRES_USER_IAM\""
  echo "export MYSQL_IAM_USER=\"\$MYSQL_USER_IAM\""
  } > "$1"

}

## help - prints the help details
##
function help() {
   # This will print the comments beginning with ## above each function
   # in this file.

   echo "build.sh <command> <arguments>"
   echo
   echo "Commands to assist with local development and CI builds."
   echo
   echo "Commands:"
   echo
   grep -e '^##' "$SCRIPT_FILE" | sed -e 's/##/ /'
}

set -euo pipefail

# Check CLI Arguments
if [[ "$#" -lt 1 ]] ; then
  help
  exit 1
fi

cd "$SCRIPT_DIR"

"$@"

