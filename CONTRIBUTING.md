# How to Contribute

We'd love to accept your patches and contributions to this project. There are
just a few small guidelines you need to follow.

## Contributor License Agreement

Contributions to this project must be accompanied by a Contributor License
Agreement. You (or your employer) retain the copyright to your contribution;
this simply gives us permission to use and redistribute your contributions as
part of the project. Head over to <https://cla.developers.google.com/> to see
your current agreements on file or to sign a new one.

You generally only need to submit a CLA once, so if you've already submitted one
(even if it was for a different project), you probably don't need to do it
again.

## Community Guidelines

This project follows
[Google's Open Source Community Guidelines](https://opensource.google.com/conduct/).

## Code reviews

All submissions, including submissions by project members, require review. We
use GitHub pull requests for this purpose. Consult
[GitHub Help](https://help.github.com/articles/about-pull-requests/) for more
information on using pull requests.

## Running Tests

Tests can be run with `nox`. You can install nox with `pip install nox`.

### Unit Tests

To run all unit tests use `nox -s unit-<PYTHON_MAJOR_VERSION>` with the major
Python version you have activated in your environment.

For example, to run the unit tests against Python 3.11 you would run
`nox -s unit-3.11`

### System/Integration Tests

To run all integration tests against real Cloud SQL instances
(Postgres, MySQL and SQL Server) there is some setup involved.

#### Initial Setup

1. Enable the Cloud SQL Admin API within your Google Cloud Project.
  `gcloud services enable sqladmin.googleapis.com`
1. This library uses [Application Default Credentials (ADC)][adc]] to
  source credentials. Whichever credential you use must have the
  Cloud SQL Client role (or equivalent permissions) and the Cloud SQL
  Instance User role (for automatic IAM authentication tests).
1. You'll need to create several Cloud SQL instances - one for MySQL, Postgres,
  and SQL Server (MySQL and Postgres require IAM authentication flag enabled).
1. Once created, set the following environment variables:

```sh
export MYSQL_CONNECTION_NAME="<PROJECT>:<REGION>:<INSTANCE>"
export MYSQL_USER="db_user"
export MYSQL_PASS="db_pass"
export MYSQL_DB="db_name"
# MySQL instance with IAM authentication enabled
# (can be same as MYSQL_CONNECTION_NAME)
export MYSQL_IAM_CONNECTION_NAME="<PROJECT>:<REGION>:<INSTANCE>"
# IAM Principal of ADC sourced credentials (truncated)
export MYSQL_IAM_USER="test-user@gmail.com"

export POSTGRES_CONNECTION_NAME="<PROJECT>:<REGION>:<INSTANCE>"
export POSTGRES_USER="db_user"
export POSTGRES_PASS="db_pass"
export POSTGRES_DB="db_name"
# Postgres instance with IAM authentication enabled
# (can be same as POSTGRES_CONNECTION_NAME)
export POSTGRES_IAM_CONNECTION_NAME="<PROJECT>:<REGION>:<INSTANCE>"
# IAM Principal of ADC sourced credentials
export POSTGRES_IAM_USER="test-user@gmail.com"

export SQLSERVER_CONNECTION_NAME="<PROJECT>:<REGION>:<INSTANCE>"
export SQLSERVER_USER="db_user"
export SQLSERVER_PASS="db_pass"
export SQLSERVER_DB="db_name"
```

#### Running System/Integration Tests

To run all integrations tests use `nox -s system-<PYTHON_MAJOR_VERSION>` with the major
Python version you have activated in your environment.

For example, to run the integration tests against Python 3.11 you would run
`nox -s system-3.11`

### Running Individual Files or Tests

Individual test files or tests can be run with `pytest`.

To run an individual test file run:

```sh
python -m pytest path/to/test.py
```

To run an individual test case run:

```sh
python -m pytest path/to/test.py::test_name
```

[adc]: https://cloud.google.com/docs/authentication/best-practices-applications#overview_of_application_default_credentials
