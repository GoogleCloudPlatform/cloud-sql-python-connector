# Cloud SQL Connector for Python Drivers
**Warning**: This project is currently in _alpha_, and releases may contain breaking API changes.

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

To activate credentials locally, use the following `gcloud` command:

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

To use the connector: import the connector by including the following statement at the top of your Python file:
```Python
from google.cloud.sql.connector import connector
```

Use the connector to create a connection object by calling the connect method. Input your connection string as the first positional argument and the name of the database driver for the second positional argument. Insert the rest of your connection keyword arguments like user, password and database. You can also set the optional `timeout` or `ip_type` keyword arguments.

```
conn = connector.connect(
    "project:region:instance",
    "pymysql",
    user="root",
    password="shhh",
    db="your-db-name"
... insert other kwargs ...
)
```

The returned DB-API 2.0 compliant connection object can then be used to query and modify the database:
```
# Execute a query
cursor = conn.cursor()
cursor.execute("SELECT * from my_table")

# Fetch the results
result = cursor.fetchall()

# Do something with the results
for row in result:
    print(row)
```

To use this connector with SQLAlchemy, use the `creator` argument for `sqlalchemy.create_engine`:
```
def getconn() -> pymysql.connections.Connection:
    conn: pymysql.connections.Connection = connector.connect(
        "project:region:instance",
        "pymysql",
        user="root",
        password="shhh",
        db="your-db-name"
    )
    return conn

engine = sqlalchemy.create_engine(
    "mysql+pymysql://",
    creator=getconn,
)
```

**Note for SQL Server users**: If your SQL Server instance requires SSL, you need to download the CA certificate for your instance and include `cafile={path to downloaded certificate}` and `validate_host=False`. This is a workaround for a [known issue](https://issuetracker.google.com/184867147).

### Specifying Public or Private IP
The Cloud SQL Connector for Python can be used to connect to Cloud SQL instances using both public and private IP addresses. To specify which IP address to use to connect, set the `ip_type` keyword argument Possible values are `IPTypes.PUBLIC` and `IPTypes.PRIVATE`.
Example:
```
connector.connect(
    "project:region:instance",
    "pymysql",
    ip_types=IPTypes.PRIVATE # Prefer private IP
... insert other kwargs ...
)
```

Note: If specifying Private IP, your application must already be in the same VPC network as your Cloud SQL Instance.

### IAM Authentication
Connections using [IAM database authentication](https://cloud.google.com/sql/docs/postgres/iam-logins) are supported when using the Postgres driver.
This feature is unsupported for other drivers.
First, make sure to [configure your Cloud SQL Instance to allow IAM authentication](https://cloud.google.com/sql/docs/postgres/create-edit-iam-instances#configure-iam-db-instance) and [add an IAM database user](https://cloud.google.com/sql/docs/postgres/create-manage-iam-users#creating-a-database-user).
Now, you can connect using user or service account credentials instead of a password.
In the call to connect, set the `enable_iam_auth` keyword argument to true and `user` to the email address associated with your IAM user.
Example:
```
connector.connect(
     "project:region:instance",
     "pg8000",
     user="postgres-iam-user@gmail.com",
     db="my_database",
     enable_iam_auth=True,
 )
```
### Setup for development

Tests can be run with `nox`. Change directory into the `cloud-sql-python-connector` and just run `nox` to run the tests.

1. Create a MySQL instance on Google Cloud SQL. Make sure to note your root password when creating the MySQL instance.
2. When the MySQL instance has finished creating, go to the overview page and set the instance’s connection string to the environment variable MYSQL_CONNECTION_NAME using the following command:
```
export MYSQL_CONNECTION_NAME=your:connection:string
```
3. Enable SSL for your Cloud SQL instance by following [these instructions](https://cloud.google.com/sql/docs/mysql/configure-ssl-instance).
4. Create a service account with Cloud SQL Admin and Cloud SQL Client roles, then download the key and save it in a safe location. Set the path to the json file to the environment variable GOOGLE_APPLICATION_CREDENTIALS using the following command:
```
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/auth/./json
```
5. Enable the SQL Admin API.
6. Clone the [repository](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector).
7. Create a virtual environment and change directory into the `cloud-sql-python-connector` folder.
8. Install the package by running the following command:
```
pip install .
```
