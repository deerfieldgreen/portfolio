FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY data_processing/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, SQL files, and config (context: market_regime_detection parent)
COPY data_processing/process_data.py .
COPY data_processing/enrich_data.py .
COPY data_processing/setup_tables.py .
COPY data_processing/sql/ ./sql/
COPY config.yaml .
# Config will be mounted or provided via ConfigMap

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "process_data.py"]
