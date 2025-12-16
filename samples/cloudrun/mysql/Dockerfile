# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.14-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . .

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup.
# Use gunicorn for production deployments.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
