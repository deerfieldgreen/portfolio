FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY regime_modeling/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and config (context: market_regime_detection parent)
COPY regime_modeling/train_model.py .
COPY config.yaml .
# Config will be mounted or provided via ConfigMap

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "train_model.py"]
