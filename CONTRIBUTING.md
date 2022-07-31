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

## Running tests

### Initial Setup

1. Enable the SQL Admin API.
2. This library uses [Application Default Credentials (ADC)][adc]] to 
  automatically detect credentials. Which ever credential you use must have the
  Cloud SQL client role (or equivalent permissions). 
3. You'll need to create several Cloud SQL instances - one for MySQL, Postgres,
  and SQL Server. 
2. Once created, set the following environment variables:
```
export MYSQL_CONNECTION_NAME="your:connection:string"
export MYSQL_USER="db_user"
export MYSQL_PASS="db_pass"
export MYSQL_DB="db_name"

export POSTGRES_CONNECTION_NAME="your:connection:string"
export POSTGRES_USER="db_user"
export POSTGRES_PASS="db_pass"
export POSTGRES_DB="db_name"

# This instance will need to have IAM Database authentication enabled
export POSTGRES_IAM_CONNECTION_NAME="your:connection:string"
export POSTGRES_IAM_USER="iam_user@google.com"

export SQLSERVER_CONNECTION_NAME="your:connection:string"
export SQLSERVER_USER="db_user"
export SQLSERVER_PASS="db_pass"
export SQLSERVER_DB="db_name"

export GOOGLE_APPLICATION_CREDENTIALS="location/of/application_default_credentials.json"
```

### Running tests 

Tests can be run with `nox`. You can install nox with `pip install nox`, and
run specific tests with `nox -s $SESSION_NAME`.

Note: You may need a specific version of python installed to run those tests.
For example, you'll need Python 3.8 installed to run `unit-3.8` or 
`system-3.8`.

[adc]: https://cloud.google.com/docs/authentication/best-practices-applications#overview_of_application_default_credentials
