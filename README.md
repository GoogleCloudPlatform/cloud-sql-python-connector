# Cloud SQL Connector for Python Drivers
![CI](https://storage.googleapis.com/cloud-devrel-public/cloud-sql-connectors/python/python3.10_linux.svg)
[![pypi](https://img.shields.io/pypi/v/cloud-sql-python-connector)](https://pypi.org/project/cloud-sql-python-connector)
[![python](https://img.shields.io/pypi/pyversions/cloud-sql-python-connector)](https://pypi.org/project/cloud-sql-python-connector)

**Warning**: This project is currently in _beta_. Please [open an issue](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/new/choose) if you would like to report a bug or documentation issue, request a feature, or have a question.

The Cloud SQL Python Connector is a library that can be used alongside a database driver to allow users with sufficient permissions to connect to a Cloud SQL
database without having to manually allowlist IPs or manage SSL certificates.

Currently supported drivers are
 - [`pymysql`](https://github.com/PyMySQL/PyMySQL) (MySQL)
 - [`pg8000`](https://github.com/tlocke/pg8000) (PostgreSQL)
 - [`pytds`](https://github.com/denisenkom/pytds) (SQL Server)

# Supported Python Versions
Currently Python versions >= 3.6 are supported.

### Authentication

This library uses the [Application Default Credentials](https://cloud.google.com/docs/authentication/production) to authenticate the
connection to the Cloud SQL server. For more details, see the previously
mentioned link.

To activate credentials locally ensure the Google Cloud SDK is installed on your machine. For manual installation see [Installing Cloud SDK](https://cloud.google.com/sdk/docs/install). Once installed, use the following `gcloud` command:

```
gcloud auth application-default login
```

### How to install this connector

#### Install latest release from PyPI
Upgrade to the latest version of `pip`, then run the following command, replacing `driver` with one of the driver names listed above.
```
pip install cloud-sql-python-connector[driver]
```
For example, to use the Python connector with `pymysql`, run `pip install cloud-sql-python-connector[pymysql]`

#### Install dev version
Clone this repo, `cd` into the `cloud-sql-python-connector` directory then run the following command to install the package:
```
pip install .
```
Conversely, install straight from Github using `pip`:
```
pip install git+https://github.com/GoogleCloudPlatform/cloud-sql-python-connector
```

### How to use this connector

To use the connector: import the connector and SQLAlchemy by including the following statements at the top of your Python file:
```Python
from google.cloud.sql.connector import connector
import sqlalchemy
```

The connector itself creates connection objects by calling its `connect` method but does not manage database connection pooling. For this reason, it is recommended to use the connector alongside a library that can create connection pools, such as [SQLAlchemy](https://www.sqlalchemy.org/). This will allow for connections to remain open and be reused, reducing connection overhead and the number of connections needed.

In the connector's `connect` method below, input your connection string as the first positional argument and the name of the database driver for the second positional argument. Insert the rest of your connection keyword arguments like user, password and database. You can also set the optional `timeout` or `ip_type` keyword arguments.

To use this connector with SQLAlchemy, use the `creator` argument for `sqlalchemy.create_engine`:
```python
def getconn() -> pymysql.connections.Connection:
    conn: pymysql.connections.Connection = connector.connect(
        "project:region:instance",
        "pymysql",
        user="root",
        password="shhh",
        db="your-db-name"
    )
    return conn

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

**Note**: For more examples of using SQLAlchemy to manage connection pooling with the connector, please see [Cloud SQL SQLAlchemy Samples](https://cloud.google.com/sql/docs/postgres/connect-connectors#python_1).

**Note for SQL Server users**: If your SQL Server instance requires SSL, you need to download the CA certificate for your instance and include `cafile={path to downloaded certificate}` and `validate_host=False`. This is a workaround for a [known issue](https://issuetracker.google.com/184867147).

### Specifying Public or Private IP
The Cloud SQL Connector for Python can be used to connect to Cloud SQL instances using both public and private IP addresses. To specify which IP address to use to connect, set the `ip_type` keyword argument Possible values are `IPTypes.PUBLIC` and `IPTypes.PRIVATE`.
Example:
```python
connector.connect(
    "project:region:instance",
    "pymysql",
    ip_type=IPTypes.PRIVATE # Prefer private IP
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

### Release cadence
This project aims for a minimum monthly release cadence. If no new
features or fixes have been added, a new PATCH version with the latest
dependencies is released.

### Contributing

We welcome outside contributions. Please see our 
[Contributing Guide](CONTRIBUTING.md) for details on how best to contribute. 
