# Cloud SQL Connector for Python Drivers
*Warning*: This project is experimental, and is not an officially supported Google product.

The Cloud SQL Python Connector library is a library for MySQL/Postgres Python
drivers that allows users with sufficient permissions to connect  to a Cloud SQL
database without having to manually whitelist IPs or manage SSL certificates.

### Authentication

This library uses the [Application Default Credentials](https://cloud.google.com/docs/authentication/production) to authenticate the
connection to the Cloud SQL server. For more details, see the previously
mentioned link.

To activate credentials locally, use the following `gcloud` command:

```
gcloud auth application-default login
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
5. Clone the [repository](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector).
6. Create a virtual environment and activate it by running the following commands:
```
python3.7 -m venv env
source env/bin/activate
```
7. Install the dependencies using the following command:
```
python3.7 -m pip install -r requirements.txt
```
8. To use the connector: import the connector by including the following statement at the top of your Python file:
```Python
from google.cloud.sql.connector import connector
```
9. Use the connector to create a connection object by calling the connect method. Input your connection string as the first positional argument and “mysql-connector” for the second positional argument. Insert the rest of your connection keyword arguments like user, password and database.
```
connector.connect(
    "your:connection:string:", 
    "mysql-connector",
    user="root",
    password="shhh",
    database="your-db-name"
... insert other kwargs ...
)
```