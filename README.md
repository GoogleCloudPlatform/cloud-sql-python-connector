# Cloud SQL Connector for Python Drivers
*Warning*: This project is experimental, and is not an officially supported Google product.

The Cloud SQL Python Connector library is a library for MySQL/Postgres Python
drivers that allows users with sufficient permissions to connect  to a Cloud SQL
database without having to manually allowlist IPs or manage SSL certificates.

Currently only supports MySQL through the `pymysql` driver.

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

Use the connector to create a connection object by calling the connect method. Input your connection string as the first positional argument and “mysql-connector” for the second positional argument. Insert the rest of your connection keyword arguments like user, password and database.

```
connector.connect(
    "your:connection:string:", 
    "pymysql",
    user="root",
    password="shhh",
    db="your-db-name"
... insert other kwargs ...
)
```


### Setup for development

Tests can be run with `nox`. Change directory into the `cloud-sql-python-connector` and just run `nox` to run the tests.

1. Create a MySQL instance on Google Cloud SQL. Make sure to note your root password when creating the MySQL instance. 
2. When the MySQL instance has finished creating, go to the overview page and set the instance’s connection string to the environment variable INSTANCE_CONNECTION_NAME using the following command:
```
export INSTANCE_CONNECTION_NAME=your:connection:string
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
