# Financial News Scoring Pipeline. Secrets from env only; do not load from file.
# Used by Argo CronWorkflow (fan-out per query) and standalone mode.

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY NEWS_SCORE_V1.yaml scoring_pipeline.py config.yaml ./
COPY bootstrap/ ./bootstrap/

# Default: run all queries. Argo overrides with --query-index N per task.
ENTRYPOINT ["python", "scoring_pipeline.py"]
