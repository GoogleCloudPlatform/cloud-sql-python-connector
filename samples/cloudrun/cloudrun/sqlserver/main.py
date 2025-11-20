import os
import sqlalchemy
from flask import Flask
from google.cloud.sql.connector import Connector, IPTypes
from google.cloud import secretmanager

# Initialize Flask app
app = Flask(__name__)

# Initialize the Connector object with lazy refresh
connector = Connector(refresh_strategy="lazy")

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

# Create the SQLAlchemy engine
engine = sqlalchemy.create_engine(
    "mssql+pytds://",
    creator=get_connection,
)

@app.route("/")
def index():
    try:
        with engine.connect() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchall()
            return f"Database connection successful, result: {result}"
    except Exception as e:
        return f"Error connecting to the database: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
