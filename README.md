<p align="center">
    <a href="https://cloud.google.com/blog/topics/developers-practitioners/how-connect-cloud-sql-using-python-easy-way">
        <img src="https://raw.githubusercontent.com/GoogleCloudPlatform/cloud-sql-python-connector/main/docs/images/cloud-sql-python-connector.png" alt="cloud-sql-python-connector image">
    </a>
</p>

<h1 align="center">Cloud SQL Python Connector</h1>

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/GoogleCloudPlatform/cloud-sql-python-connector/blob/main/samples/notebooks/postgres_python_connector.ipynb)
[![CI](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/actions/workflows/tests.yml/badge.svg?event=push)](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/actions/workflows/tests.yml?query=event%3Apush+branch%3Amain)
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
 - [`asyncpg`](https://github.com/MagicStack/asyncpg) (PostgreSQL)
 - [`pytds`](https://github.com/denisenkom/pytds) (SQL Server)


## Installation

You can install this library with `pip install`, specifying the driver
based on your database dialect.

### MySQL
```
pip install "cloud-sql-python-connector[pymysql]"
```
### Postgres
There are two different database drivers that are supported for the Postgres dialect:

#### pg8000
```
pip install "cloud-sql-python-connector[pg8000]"
```
#### asyncpg
```
pip install "cloud-sql-python-connector[asyncpg]"
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
resolving credentials. Please see [these instructions for how to set your ADC][set-adc]
(Google Cloud Application vs Local Development, IAM user vs service account credentials),
or consult the [google.auth][google-auth] package.

To explicitly set a specific source for the credentials, see
[Configuring the Connector](#configuring-the-connector) below.

[adc]: https://cloud.google.com/docs/authentication#adc
[set-adc]: https://cloud.google.com/docs/authentication/provide-credentials-adc
[google-auth]: https://google-auth.readthedocs.io/en/master/reference/google.auth.html

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
        user="my-user",
        password="my-password",
        db="my-db-name"
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
            user="my-user",
            password="my-password",
            db="my-db-name"
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
     db="my-db-name",
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
    db="my-db-name",
    active_directory_auth=True,
    server_name="public.[instance].[location].[project].cloudsql.[domain]",
)
```
Or, if using Private IP:
```python
connector.connect(
    "project:region:instance",
    "pytds",
    db="my-db-name",
    active_directory_auth=True,
    server_name="private.[instance].[location].[project].cloudsql.[domain]",
    ip_type=IPTypes.PRIVATE
)
```

### Using the Python Connector with Python Web Frameworks
The Python Connector can be used alongside popular Python web frameworks such
as Flask, FastAPI, etc, to integrate Cloud SQL databases within your
web applications.

#### Flask-SQLAlchemy
[Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/en/2.x/)
is an extension for [Flask](https://flask.palletsprojects.com/en/2.2.x/)
that adds support for [SQLAlchemy](https://www.sqlalchemy.org/) to your
application. It aims to simplify using SQLAlchemy with Flask by providing
useful defaults and extra helpers that make it easier to accomplish
common tasks.

You can configure Flask-SQLAlchemy to connect to a Cloud SQL database from
your web application through the following:

```python
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from google.cloud.sql.connector import Connector, IPTypes


# Python Connector database connection function
def getconn():
    with Connector() as connector:
        conn = connector.connect(
            "project:region:instance-name", # Cloud SQL Instance Connection Name
            "pg8000",
            user="my-user",
            password="my-password",
            db="my-database",
            ip_type= IPTypes.PUBLIC  # IPTypes.PRIVATE for private IP
        )
        return conn


app = Flask(__name__)

# configure Flask-SQLAlchemy to use Python Connector
app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql+pg8000://"
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "creator": getconn
}

db = SQLAlchemy(app)
```

For more details on how to use Flask-SQLAlchemy, check out the
[Flask-SQLAlchemy Quickstarts](https://flask-sqlalchemy.palletsprojects.com/en/2.x/quickstart/#)

#### FastAPI
[FastAPI](https://fastapi.tiangolo.com/) is a modern, fast (high-performance),
web framework for building APIs with Python based on standard Python type hints.

You can configure FastAPI to connect to a Cloud SQL database from
your web application using [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/14/orm/)
through the following:

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from google.cloud.sql.connector import Connector, IPTypes

# Python Connector database connection function
def getconn():
    with Connector() as connector:
        conn = connector.connect(
            "project:region:instance-name", # Cloud SQL Instance Connection Name
            "pg8000",
            user="my-user",
            password="my-password",
            db="my-database",
            ip_type= IPTypes.PUBLIC  # IPTypes.PRIVATE for private IP
        )
    return conn

SQLALCHEMY_DATABASE_URL = "postgresql+pg8000://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL , creator=getconn
)

# create SQLAlchemy ORM session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
```

To learn more about integrating a database into your FastAPI application,
follow along the [FastAPI SQL Database guide](https://fastapi.tiangolo.com/tutorial/sql-databases/#create-the-database-models).

### Async Driver Usage
The Cloud SQL Connector is compatible with
[asyncio](https://docs.python.org/3/library/asyncio.html) to improve the speed
and efficiency of database connections through concurrency. You can use all
non-asyncio drivers through the `Connector.connect_async` function, in addition
to the following asyncio database drivers:
- [asyncpg](https://magicstack.github.io/asyncpg) (Postgres)

The Cloud SQL Connector has a helper `create_async_connector` function that is
recommended for asyncio database connections. It returns a `Connector`
object that uses the current thread's running event loop. This is different
than `Connector()` which by default initializes a new event loop in a
background thread.

The `create_async_connector` allows all the same input arguments as the
[Connector](#configuring-the-connector) object.

Once a `Connector` object is returned by `create_async_connector` you can call
its `connect_async` method, just as you would the `connect` method:

```python
import asyncio
import asyncpg
from google.cloud.sql.connector import create_async_connector


async def main():
    # intialize Connector object using 'create_async_connector'
    connector = await create_async_connector()

    # create connection to Cloud SQL database
    conn: asyncpg.Connection = await connector.connect_async(
        "project:region:instance",  # Cloud SQL instance connection name
        "asyncpg",
        user="my-user",
        password="my-password",
        db="my-db-name"
        # ... additional database driver args
    )

    # insert into Cloud SQL database (example)
    await conn.execute("INSERT INTO ratings (title, genre, rating) VALUES ('Batman', 'Action', 8.2)")

    # query Cloud SQL database (example)
    results = await conn.fetch("SELECT * from ratings")

    # ... do something with results
    for row in results:
        print(row)

    # close asyncpg connection
    await conn.close()

    # close Cloud SQL Connector
    await connector.close_async()


# Test connection with `asyncio`
asyncio.run(main())
```

For more details on interacting with an `asyncpg.Connection`, please visit
the [official documentation](https://magicstack.github.io/asyncpg/current/api/index.html).

### Async Context Manager

An alternative to using the `create_async_connector` function is initializing
a `Connector` as an async context manager, removing the need for explicit
calls to `connector.close_async()` to cleanup resources.

**Note:** This alternative requires that the running event loop be
passed in as the `loop` argument to `Connector()`.

```python
import asyncio
import asyncpg
from google.cloud.sql.connector import Connector

async def main():
    # get current running event loop to be used with Connector
    loop = asyncio.get_running_loop()
    # intialize Connector object as async context manager
    async with Connector(loop=loop) as connector:

        # create connection to Cloud SQL database
        conn: asyncpg.Connection = await connector.connect_async(
            "project:region:instance",  # Cloud SQL instance connection name
            "asyncpg",
            user="my-user",
            password="my-password",
            db="my-db-name"
            # ... additional database driver args
        )

        # insert into Cloud SQL database (example)
        await conn.execute("INSERT INTO ratings (title, genre, rating) VALUES ('Batman', 'Action', 8.2)")

        # query Cloud SQL database (example)
        results = await conn.fetch("SELECT * from ratings")

        # ... do something with results
        for row in results:
            print(row)

        # close asyncpg connection
        await conn.close()

# Test connection with `asyncio`
asyncio.run(main())
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
