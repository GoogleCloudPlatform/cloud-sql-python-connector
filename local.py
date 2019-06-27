from connector import get_ephemeral
from utils import generate_keys
import google.auth

from googleapiclient import discovery
from dotenv import load_dotenv

def google_csql_authentication():
    credentials, project = google.auth.default()
    scoped_credentials = credentials.with_scopes(
        [
            'https://www.googleapis.com/auth/sqlservice.admin',
            'https://www.googleapis.com/auth/cloud-platform'
        ]
    )
    cloudsql = discovery.build(
        'sqladmin',
        'v1beta4',
        credentials=scoped_credentials
    )
    return cloudsql


load_dotenv()
priv_key, pub_key = generate_keys()
csql = google_csql_authentication()

instance_name = "test"
project_name = "test"

ephemeral = get_ephemeral(
    csql,
    project_name,
    instance_name,
    pub_key.decode('UTF-8')
)

print(ephemeral)
