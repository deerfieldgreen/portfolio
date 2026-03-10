# docker/orchestrator.Dockerfile
FROM python:3.11-slim

COPY argo_pipelines/data_scientist_agent_swarm_research/requirements-orchestrator.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-orchestrator.txt

COPY argo_pipelines/data_scientist_agent_swarm_research/src/shared/ /app/src/shared/
COPY argo_pipelines/data_scientist_agent_swarm_research/src/swarm/ /app/src/swarm/
WORKDIR /app
ENTRYPOINT ["python", "-m", "src.swarm.graph"]
