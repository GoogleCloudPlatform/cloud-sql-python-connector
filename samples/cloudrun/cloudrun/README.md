# Connecting Cloud Run to Cloud SQL with the Python Connector

This guide provides a comprehensive walkthrough of how to connect a Cloud Run service to a Cloud SQL instance using the Cloud SQL Python Connector. It covers connecting to instances with both public and private IP addresses and demonstrates how to handle database credentials securely.

## Develop a Python Application

The following Python applications demonstrate how to connect to a Cloud SQL instance using the Cloud SQL Python Connector.

### `mysql/main.py` and `postgres/main.py`

These files contain the core application logic for connecting to a Cloud SQL for MySQL or PostgreSQL instance. They provide two separate authentication methods, each exposed at a different route:
- `/`: Password-based authentication
- `/iam`: IAM-based authentication


### `sqlserver/main.py`

This file contains the core application logic for connecting to a Cloud SQL for SQL Server instance. It uses the `cloud-sql-python-connector` to create a SQLAlchemy connection pool with password-based authentication at the `/` route.

> [!NOTE]
>
> Cloud SQL for SQL Server does not support IAM database authentication.


> [!NOTE]
> **Lazy Refresh**
>
> The sample code in all three `main.py` files initializes the `Connector` with `refresh_strategy=lazy`. This is a recommended approach to avoid connection errors and optimize cost by preventing background processes from running when the CPU is throttled.

## IAM Authentication Prerequisites


For IAM authentication to work, you must ensure two things:

1.  **The Cloud Run service's service account has the `Cloud SQL Client` role.** You can grant this role with the following command:
    ```bash
    gcloud projects add-iam-policy-binding PROJECT_ID \
        --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
        --role="roles/cloudsql.client"
    ```
    Replace `PROJECT_ID` with your Google Cloud project ID and `SERVICE_ACCOUNT_EMAIL` with the email of the service account your Cloud Run service is using.

2.  **The service account is added as a database user to your Cloud SQL instance.** You can do this with the following command:
    ```bash
    gcloud sql users create SERVICE_ACCOUNT_EMAIL \
        --instance=INSTANCE_NAME \
        --type=cloud_iam_user
    ```
    Replace `SERVICE_ACCOUNT_EMAIL` with the same service account email and `INSTANCE_NAME` with your Cloud SQL instance name.

## Deploy the Application to Cloud Run

Follow these steps to deploy the application to Cloud Run.

### Build and Push the Docker Image

1.  **Enable the Artifact Registry API:**

    ```bash
    gcloud services enable artifactregistry.googleapis.com
    ```

2.  **Create an Artifact Registry repository:**

    ```bash
    gcloud artifacts repositories create REPO_NAME \
      --repository-format=docker \
      --location=REGION
    ```

3.  **Configure Docker to authenticate with Artifact Registry:**

    ```bash
    gcloud auth configure-docker REGION-docker.pkg.dev
    ```

4.  **Build the Docker image (replace `mysql` with `postgres` or `sqlserver` as needed):**

    ```bash
    docker build -t REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME mysql
    ```

5.  **Push the Docker image to Artifact Registry:**

    ```bash
    docker push REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME
    ```

### Deploy to Cloud Run

Deploy the container image to Cloud Run using the `gcloud run deploy` command.


**Sample Values:**
*   `SERVICE_NAME`: `my-cloud-run-service`
*   `REGION`: `us-central1`
*   `PROJECT_ID`: `my-gcp-project-id`
*   `REPO_NAME`: `my-artifact-repo`
*   `IMAGE_NAME`: `my-app-image`
*   `INSTANCE_CONNECTION_NAME`: `my-gcp-project-id:us-central1:my-instance-name`
*   `DB_USER`: `my-db-user` (for password-based authentication)
*   `DB_IAM_USER`: `my-service-account@my-gcp-project-id.iam.gserviceaccount.com` (for IAM-based authentication)
*   `DB_NAME`: `my-db-name`
*   `DB_SECRET_NAME`: `projects/my-gcp-project-id/secrets/my-db-secret/versions/latest`
*   `VPC_NETWORK`: `my-vpc-network`
*   `SUBNET_NAME`: `my-vpc-subnet`


**For MySQL and PostgreSQL (Public IP):**

```bash
gcloud run deploy SERVICE_NAME \
  --image=REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME \
  --add-cloudsql-instances=INSTANCE_CONNECTION_NAME \
  --set-env-vars=DB_USER=DB_USER,DB_IAM_USER=DB_IAM_USER,DB_NAME=DB_NAME,DB_SECRET_NAME=DB_SECRET_NAME,INSTANCE_CONNECTION_NAME=INSTANCE_CONNECTION_NAME \
  --region=REGION
```

**For MySQL and PostgreSQL (Private IP):**

```bash
gcloud run deploy SERVICE_NAME \
  --image=REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME \
  --add-cloudsql-instances=INSTANCE_CONNECTION_NAME \
  --set-env-vars=DB_USER=DB_USER,DB_IAM_USER=DB_IAM_USER,DB_NAME=DB_NAME,DB_SECRET_NAME=DB_SECRET_NAME,INSTANCE_CONNECTION_NAME=INSTANCE_CONNECTION_NAME,IP_TYPE=PRIVATE \
  --network=VPC_NETWORK \
  --subnet=SUBNET_NAME \
  --vpc-egress=private-ranges-only \
  --region=REGION
```

**For SQL Server (Public IP):**

```bash
gcloud run deploy SERVICE_NAME \
  --image=REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME \
  --add-cloudsql-instances=INSTANCE_CONNECTION_NAME \
  --set-env-vars=DB_USER=DB_USER,DB_NAME=DB_NAME,DB_SECRET_NAME=DB_SECRET_NAME,INSTANCE_CONNECTION_NAME=INSTANCE_CONNECTION_NAME \
  --region=REGION
```

**For SQL Server (Private IP):**

```bash
gcloud run deploy SERVICE_NAME \
  --image=REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_name \
  --add-cloudsql-instances=INSTANCE_CONNECTION_NAME \
  --set-env-vars=DB_USER=DB_USER,DB_NAME=DB_NAME,DB_SECRET_NAME=DB_SECRET_NAME,INSTANCE_CONNECTION_NAME=INSTANCE_CONNECTION_NAME,IP_TYPE=PRIVATE \
  --network=VPC_NETWORK \
  --subnet=SUBNET_NAME \
  --vpc-egress=private-ranges-only \
  --region=REGION
```

> [!NOTE]
> **`For PSC connections`**
>
> To connect to the Cloud SQL instance with PSC connection type, create a PSC endpoint, a DNS zone and DNS record for the instance in the same VPC network as the Cloud Run service and replace the `IP_TYPE` in the deploy command with `PSC`. To configure DNS records, refer to [Connect to an instance using Private Service Connect](https://docs.cloud.google.com/sql/docs/mysql/configure-private-service-connect) guide