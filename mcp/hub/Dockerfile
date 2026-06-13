# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install git for the git connector
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# MCP communicates on stdio – no port EXPOSE needed
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "main.py"]
