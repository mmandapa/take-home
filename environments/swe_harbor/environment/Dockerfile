FROM python:3.11-slim

WORKDIR /app

# Install system deps for pycurl
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libcurl4-openssl-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY app/ /app/

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pytest && \
    python manage.py migrate --run-syncdb && \
    python manage.py compress --force 2>/dev/null || true
