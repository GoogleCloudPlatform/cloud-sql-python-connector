# Cloud SQL Connector for Python Drivers
--------------------------------------------
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

