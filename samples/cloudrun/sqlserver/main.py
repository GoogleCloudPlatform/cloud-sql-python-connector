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
from google.cloud import secretmanager

# Initialize Flask app
app = Flask(__name__)

# Connector and SQLAlchemy engine are initialized as None to allow for lazy instantiation.
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
engine = None


def get_connection() -> sqlalchemy.engine.base.Connection:
    """
    Function to create a database connection.
    This function will be used by SQLAlchemy as a creator.
    """
    instance_connection_name = os.environ["INSTANCE_CONNECTION_NAME"]
    db_user = os.environ["DB_USER"]
    db_name = os.environ["DB_NAME"]
    db_secret_name = os.environ["DB_SECRET_NAME"]
    ip_type_str = os.environ.get("IP_TYPE", "PUBLIC")
    ip_type = IPTypes[ip_type_str]

    # Get the database password from Secret Manager
    secret_client = secretmanager.SecretManagerServiceClient()
    secret_response = secret_client.access_secret_version(name=db_secret_name)
    db_password = secret_response.payload.data.decode("UTF-8")

    # Connect to the database
    conn = connector.connect(
        instance_connection_name,
        "pytds",
        user=db_user,
        password=db_password,
        db=db_name,
        ip_type=ip_type,
    )
    return conn


def connect_to_db() -> sqlalchemy.engine.base.Connection:
    """Initializes the connector and engine if necessary, then returns a connection."""
    global connector, engine

    if connector is None:
        connector = Connector(refresh_strategy="lazy")

    if engine is None:
        engine = sqlalchemy.create_engine(
            "mssql+pytds://",
            creator=get_connection,
        )

    return engine.connect()


@app.route("/")
def index():
    try:
        with connect_to_db() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchall()
            return f"Database connection successful, result: {result}"
    except Exception as e:
        return f"Error connecting to the database", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
