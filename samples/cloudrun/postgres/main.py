"""
Copyright 2025 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
import sqlalchemy
from flask import Flask
from google.cloud.sql.connector import Connector, IPTypes

# Initialize Flask app
app = Flask(__name__)

# Connector and SQLAlchemy engines are initialized as None to allow for lazy instantiation.
#
# The Connector object is a global variable to ensure that the same connector
# instance is used across all requests. This prevents the unnecessary creation
# of new Connector instances, which is inefficient and can lead to connection
# limits being reached.
#
# Lazy instantiation (initializing the Connector and Engine only when needed)
# allows the Cloud Run service to start up faster, as it avoids performing
# initialization tasks (like fetching secrets or metadata) during startup.
connector = None
iam_engine = None
password_engine = None


# Function to create a database connection using IAM authentication
def get_iam_connection() -> sqlalchemy.engine.base.Connection:
    """Creates a database connection using IAM authentication."""
    instance_connection_name = os.environ["INSTANCE_CONNECTION_NAME"]
    db_user = os.environ["DB_IAM_USER"]  # IAM service account email
    db_name = os.environ["DB_NAME"]
    ip_type_str = os.environ.get("IP_TYPE", "PUBLIC")
    ip_type = IPTypes[ip_type_str]

    conn = connector.connect(
        instance_connection_name,
        "pg8000",
        user=db_user,
        db=db_name,
        ip_type=ip_type,
        enable_iam_auth=True,
    )
    return conn


# Function to create a database connection using password-based authentication
def get_password_connection() -> sqlalchemy.engine.base.Connection:
    """Creates a database connection using password authentication."""
    instance_connection_name = os.environ["INSTANCE_CONNECTION_NAME"]
    db_user = os.environ["DB_USER"]  # Database username
    db_name = os.environ["DB_NAME"]
    db_password = os.environ["DB_PASSWORD"]
    ip_type_str = os.environ.get("IP_TYPE", "PUBLIC")
    ip_type = IPTypes[ip_type_str]


    conn = connector.connect(
        instance_connection_name,
        "pg8000",
        user=db_user,
        password=db_password,
        db=db_name,
        ip_type=ip_type,
    )
    return conn


# This example uses two distinct SQLAlchemy engines to demonstrate two different
# authentication methods (IAM and password-based) in the same application.
#
# In a typical production application, you would generally only need one
# SQLAlchemy engine, configured for your preferred authentication method.
# Both engines are defined globally to allow for connection pooling and
# reuse across requests.


def connect_with_password() -> sqlalchemy.engine.base.Connection:
    """Initializes the connector and password engine if necessary, then returns a connection."""
    global connector, password_engine

    if connector is None:
        connector = Connector(refresh_strategy="lazy")

    if password_engine is None:
        password_engine = sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=get_password_connection,
        )

    return password_engine.connect()


def connect_with_iam() -> sqlalchemy.engine.base.Connection:
    """Initializes the connector and IAM engine if necessary, then returns a connection."""
    global connector, iam_engine

    if connector is None:
        connector = Connector(refresh_strategy="lazy")

    if iam_engine is None:
        iam_engine = sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=get_iam_connection,
        )

    return iam_engine.connect()


@app.route("/")
def password_auth_index():
    try:
        with connect_with_password() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchall()
            return f"Database connection successful (password authentication), result: {result}"
    except Exception as e:
        return f"Error connecting to the database (password authentication)", 500


@app.route("/iam")
def iam_auth_index():
    try:
        with connect_with_iam() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchall()
            return f"Database connection successful (IAM authentication), result: {result}"
    except Exception as e:
        return f"Error connecting to the database (IAM authentication)", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
