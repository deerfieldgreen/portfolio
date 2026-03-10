# docker/ops.Dockerfile — LIGHTWEIGHT OPS
FROM python:3.11-slim

COPY argo_pipelines/data_scientist_agent_swarm_research/requirements-ops.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-ops.txt

COPY argo_pipelines/data_scientist_agent_swarm_research/src/shared/ /app/src/shared/
COPY argo_pipelines/data_scientist_agent_swarm_research/src/serving/__init__.py /app/src/serving/__init__.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/serving/aggregate_cross_tf.py /app/src/serving/aggregate_cross_tf.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/serving/validate.py /app/src/serving/validate.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/promotion_gate.py /app/src/training/promotion_gate.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/validate_data.py /app/src/training/validate_data.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/extract_training_data.py /app/src/training/extract_training_data.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/cpcv/ /app/src/cpcv/
COPY argo_pipelines/data_scientist_agent_swarm_research/k8s/ /app/k8s/
COPY argo_pipelines/data_scientist_agent_swarm_research/scripts/ /app/scripts/
WORKDIR /app
ENTRYPOINT ["python", "-m"]
