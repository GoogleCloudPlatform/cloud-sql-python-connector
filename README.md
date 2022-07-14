# Cloud SQL Connector for Python Drivers
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/GoogleCloudPlatform/cloud-sql-python-connector/blob/main/samples/notebooks/postgres_python_connector.ipynb)
![CI](https://storage.googleapis.com/cloud-devrel-public/cloud-sql-connectors/python/python3.10_linux.svg)
[![pypi](https://img.shields.io/pypi/v/cloud-sql-python-connector)](https://pypi.org/project/cloud-sql-python-connector)
[![python](https://img.shields.io/pypi/pyversions/cloud-sql-python-connector)](https://pypi.org/project/cloud-sql-python-connector)

**Warning**: This project is currently in _beta_. Please [open an issue](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/new/choose) if you would like to report a bug or documentation issue, request a feature, or have a question.

The _Cloud SQL Python Connector_ is a Cloud SQL connector designed for use with the
Python language. Using a Cloud SQL connector provides the following benefits:
* **IAM Authorization:** uses IAM permissions to control who/what can connect to
  your Cloud SQL instances
* **Improved Security:** uses robust, updated TLS 1.3 encryption and
  identity verification between the client connector and the server-side proxy,
  independent of the database protocol.
* **Convenience:** removes the requirement to use and distribute SSL
  certificates, as well as manage firewalls or source/destination IP addresses.
* (optionally) **IAM DB Authentication:** provides support for
  [Cloud SQL’s automatic IAM DB AuthN][iam-db-authn] feature.

[iam-db-authn]: https://cloud.google.com/sql/docs/postgres/authentication

The Cloud SQL Python Connector is a package to be used alongside a database driver.
Currently supported drivers are:
 - [`pymysql`](https://github.com/PyMySQL/PyMySQL) (MySQL)
 - [`pg8000`](https://github.com/tlocke/pg8000) (PostgreSQL)
 - [`pytds`](https://github.com/denisenkom/pytds) (SQL Server)


## Installation

You can install this library with `pip install`, specifying the driver
based on your database dialect.

### MySQL
```
pip install "cloud-sql-python-connector[pymysql]"
```
### Postgres
```
pip install "cloud-sql-python-connector[pg8000]"
```
### SQL Server
```
pip install "cloud-sql-python-connector[pytds]"
```
## Usage

This package provides several functions for authorizing and encrypting
connections. These functions are used with your database driver to connect to
your Cloud SQL instance.

The instance connection name for your Cloud SQL instance is always in the
format "project:region:instance".

### APIs and Services

This package requires the following to successfully make Cloud SQL Connections:

- IAM principal (user, service account, etc.) with the
[Cloud SQL Client][client-role] role. This IAM principal will be used for
[credentials](#credentials).
- The [Cloud SQL Admin API][admin-api] to be enabled within your Google Cloud
Project. By default, the API will be called in the project associated with
the IAM principal.

[admin-api]: https://console.cloud.google.com/apis/api/sqladmin.googleapis.com
[client-role]: https://cloud.google.com/sql/docs/mysql/roles-and-permissions

### Credentials

This library uses the [Application Default Credentials (ADC)][adc] strategy for
resolving credentials. Please see the [google.auth][google-auth] package 
documentation for more information on how these credentials are sourced.

To activate credentials locally the recommended approach is to ensure the Google
Cloud SDK is installed on your machine. For manual installation see
[Installing Cloud SDK][cloud-sdk]. 

Once installed, use the following `gcloud` command:
```
gcloud auth application-default login
```

To explicitly set a specific source for the credentials to use, see
[Configuring the Connector](#configuring-the-connector) below.

[adc]: https://cloud.google.com/docs/authentication
[google-auth]: https://google-auth.readthedocs.io/en/master/reference/google.auth.html
[cloud-sdk]: https://cloud.google.com/sdk/docs/install

### How to use this Connector

To connect to Cloud SQL using the connector, inititalize a `Connector`
object and call it's `connect` method with the proper input parameters.

The `Connector` itself creates connection objects by calling its `connect` method but does not manage database connection pooling. For this reason, it is recommended to use the connector alongside a library that can create connection pools, such as [SQLAlchemy](https://www.sqlalchemy.org/). This will allow for connections to remain open and be reused, reducing connection overhead and the number of connections needed.

In the Connector's `connect` method below, input your connection string as the first positional argument and the name of the database driver for the second positional argument. Insert the rest of your connection keyword arguments like user, password and database. You can also set the optional `timeout` or `ip_type` keyword arguments.

To use this connector with SQLAlchemy, use the `creator` argument for `sqlalchemy.create_engine`:
```python
from google.cloud.sql.connector import Connector
import sqlalchemy

# initialize Connector object
connector = Connector()

# function to return the database connection
def getconn() -> pymysql.connections.Connection:
    conn: pymysql.connections.Connection = connector.connect(
        "project:region:instance",
        "pymysql",
        user="root",
        password="shhh",
        db="your-db-name"
    )
    return conn

# create connection pool
pool = sqlalchemy.create_engine(
    "mysql+pymysql://",
    creator=getconn,
)
```

The returned connection pool engine can then be used to query and modify the database.
```python
# insert statement
insert_stmt = sqlalchemy.text(
    "INSERT INTO my_table (id, title) VALUES (:id, :title)",
)

with pool.connect() as db_conn:
    # insert into database
    db_conn.execute(insert_stmt, id="book1", title="Book One")

    # query database
    result = db_conn.execute("SELECT * from my_table").fetchall()

    # Do something with the results
    for row in result:
        print(row)
```

To close the `Connector` object's background resources, call it's `close()` method as follows:

```python
connector.close()
```

**Note**: For more examples of using SQLAlchemy to manage connection pooling with the connector, please see [Cloud SQL SQLAlchemy Samples](https://cloud.google.com/sql/docs/postgres/connect-connectors#python_1).

**Note for SQL Server users**: If your SQL Server instance requires SSL, you need to download the CA certificate for your instance and include `cafile={path to downloaded certificate}` and `validate_host=False`. This is a workaround for a [known issue](https://issuetracker.google.com/184867147).

### Configuring the Connector

If you need to customize something about the connector, or want to specify
defaults for each connection to make, you can initialize a 
`Connector` object as follows:

```python
from google.cloud.sql.connector import Connector, IPTypes

# Note: all parameters below are optional
connector = Connector(
    ip_type=IPTypes.PUBLIC,
    enable_iam_auth=False,
    timeout=30,
    credentials=custom_creds # google.auth.credentials.Credentials
)
```

### Using Connector as a Context Manager

The `Connector` object can also be used as a context manager in order to
automatically close and cleanup resources, removing the need for explicit
calls to `connector.close()`.

Connector as a context manager:

```python
from google.cloud.sql.connector import Connector

# build connection
def getconn() -> pymysql.connections.Connection:
    with Connector() as connector:
        conn = connector.connect(
            "project:region:instance",
            "pymysql",
            user="root",
            password="shhh",
            db="your-db-name"
        )
    return conn

# create connection pool
pool = sqlalchemy.create_engine(
    "mysql+pymysql://",
    creator=getconn,
)

# insert statement
insert_stmt = sqlalchemy.text(
    "INSERT INTO my_table (id, title) VALUES (:id, :title)",
)

# interact with Cloud SQL database using connection pool
with pool.connect() as db_conn:
    # insert into database
    db_conn.execute(insert_stmt, id="book1", title="Book One")

    # query database
    result = db_conn.execute("SELECT * from my_table").fetchall()

    # Do something with the results
    for row in result:
        print(row)
```

### Specifying Public or Private IP
The Cloud SQL Connector for Python can be used to connect to Cloud SQL instances using both public and private IP addresses. To specify which IP address to use to connect, set the `ip_type` keyword argument Possible values are `IPTypes.PUBLIC` and `IPTypes.PRIVATE`.
Example:
```python
from google.cloud.sql.connector import IPTypes

connector.connect(
    "project:region:instance",
    "pymysql",
    ip_type=IPTypes.PRIVATE # use private IP
... insert other kwargs ...
)
```

Note: If specifying Private IP, your application must already be in the same VPC network as your Cloud SQL Instance.

### IAM Authentication
Connections using [Automatic IAM database authentication](https://cloud.google.com/sql/docs/postgres/authentication#automatic) are supported when using the Postgres driver. This feature is unsupported for other drivers. If automatic IAM authentication is not supported for your driver, you can use [Manual IAM database authentication](https://cloud.google.com/sql/docs/postgres/authentication#manual) to connect.
First, make sure to [configure your Cloud SQL Instance to allow IAM authentication](https://cloud.google.com/sql/docs/postgres/create-edit-iam-instances#configure-iam-db-instance) and [add an IAM database user](https://cloud.google.com/sql/docs/postgres/create-manage-iam-users#creating-a-database-user).
Now, you can connect using user or service account credentials instead of a password.
In the call to connect, set the `enable_iam_auth` keyword argument to true and `user` to the email address associated with your IAM user.
Example:
```python
connector.connect(
     "project:region:instance",
     "pg8000",
     user="postgres-iam-user@gmail.com",
     db="my_database",
     enable_iam_auth=True,
 )
```

### SQL Server Active Directory Authentication
Active Directory authentication for SQL Server instances is currently only supported on Windows. First, make sure to follow [these steps](https://cloud.google.com/blog/topics/developers-practitioners/creating-sql-server-instance-integrated-active-directory-using-google-cloud-sql) to set up a Managed AD domain and join your Cloud SQL instance to the domain. [See here for more info on Cloud SQL Active Directory integration](https://cloud.google.com/sql/docs/sqlserver/ad).

Once you have followed the steps linked above, you can run the following code to return a connection object:
```python
connector.connect(
    "project:region:instance",
    "pytds",
    db="my_database",
    active_directory_auth=True,
    server_name="public.[instance].[location].[project].cloudsql.[domain]",
)
``` 
Or, if using Private IP:
```python
connector.connect(
    "project:region:instance",
    "pytds",
    db="my_database",
    active_directory_auth=True,
    server_name="private.[instance].[location].[project].cloudsql.[domain]",
    ip_type=IPTypes.PRIVATE
)
``` 

## Support policy

### Major version lifecycle
This project uses [semantic versioning](https://semver.org/), and uses the
following lifecycle regarding support for a major version:

**Active** - Active versions get all new features and security fixes (that
wouldn’t otherwise introduce a breaking change). New major versions are
guaranteed to be "active" for a minimum of 1 year.
**Deprecated** - Deprecated versions continue to receive security and critical
bug fixes, but do not receive new features. Deprecated versions will be publicly
supported for 1 year.
**Unsupported** - Any major version that has been deprecated for >=1 year is
considered publicly unsupported.

## Supported Python Versions

We test and support at a minimum, every [active version until it's
end-of-life date][pyver]. Changes in supported Python versions will be
considered a minor change, and will be listed in the release notes. 

[pyver]: https://devguide.python.org/#status-of-python-branches

### Release cadence
This project aims for a minimum monthly release cadence. If no new
features or fixes have been added, a new PATCH version with the latest
dependencies is released.

### Contributing

We welcome outside contributions. Please see our 
[Contributing Guide](CONTRIBUTING.md) for details on how best to contribute. 
