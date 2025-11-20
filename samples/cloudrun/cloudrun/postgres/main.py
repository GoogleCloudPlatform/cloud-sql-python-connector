import os
import sqlalchemy
from flask import Flask
from google.cloud.sql.connector import Connector, IPTypes
from google.cloud import secretmanager

# Initialize Flask app
app = Flask(__name__)

# Initialize the Connector object with lazy refresh
connector = Connector(refresh_strategy="lazy")
secret_client = secretmanager.SecretManagerServiceClient()

# Function to create a database connection using IAM authentication
def get_iam_connection() -> sqlalchemy.engine.base.Connection:
    instance_connection_name = os.environ["INSTANCE_CONNECTION_NAME"]
    db_user = os.environ["DB_IAM_USER"] # IAM service account email
    db_name = os.environ["DB_NAME"]
    ip_type_str = os.environ.get("IP_TYPE", "PUBLIC")
    ip_type = IPTypes[ip_type_str]

    conn = connector.connect(
        instance_connection_name,
        "pg8000",
        user=db_user,
        db=db_name,
        ip_type=ip_type,
        enable_iam_auth=True
    )
    return conn

# Function to create a database connection using password-based authentication
def get_password_connection() -> sqlalchemy.engine.base.Connection:
    instance_connection_name = os.environ["INSTANCE_CONNECTION_NAME"]
    db_user = os.environ["DB_USER"] # Database username
    db_name = os.environ["DB_NAME"]
    db_secret_name = os.environ["DB_SECRET_NAME"]
    ip_type_str = os.environ.get("IP_TYPE", "PUBLIC")
    ip_type = IPTypes[ip_type_str]

    secret_response = secret_client.access_secret_version(name=db_secret_name)
    db_password = secret_response.payload.data.decode("UTF-8")

    conn = connector.connect(
        instance_connection_name,
        "pg8000",
        user=db_user,
        password=db_password,
        db=db_name,
        ip_type=ip_type,
    )
    return conn

# Create the SQLAlchemy engines
iam_engine = sqlalchemy.create_engine(
    "postgresql+pg8000://",
    creator=get_iam_connection,
)
password_engine = sqlalchemy.create_engine(
    "postgresql+pg8000://",
    creator=get_password_connection,
)

@app.route("/")
def password_auth_index():
    try:
        with password_engine.connect() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchall()
            return f"Database connection successful (password authentication), result: {result}"
    except Exception as e:
        return f"Error connecting to the database (password authentication): {e}", 500

@app.route("/iam")
def iam_auth_index():
    try:
        with iam_engine.connect() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchall()
            return f"Database connection successful (IAM authentication), result: {result}"
    except Exception as e:
        return f"Error connecting to the database (IAM authentication): {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
