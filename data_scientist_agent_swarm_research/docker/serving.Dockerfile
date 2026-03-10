# docker/serving.Dockerfile
FROM python:3.11-slim

COPY argo_pipelines/data_scientist_agent_swarm_research/requirements-serving.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-serving.txt
# torch CPU-only for pyfunc model loading
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY argo_pipelines/data_scientist_agent_swarm_research/src/shared/ /app/src/shared/
COPY argo_pipelines/data_scientist_agent_swarm_research/src/serving/ /app/src/serving/
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/features.py /app/src/training/features.py
WORKDIR /app
ENTRYPOINT ["python", "-m"]
