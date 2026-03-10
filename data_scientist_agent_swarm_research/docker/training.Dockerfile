# docker/training.Dockerfile — GENERIC EXECUTOR
FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime AS base

RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY argo_pipelines/data_scientist_agent_swarm_research/requirements-training.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-training.txt

COPY argo_pipelines/data_scientist_agent_swarm_research/src/shared/ /app/src/shared/
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/executor.py /app/src/training/executor.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/scaffolding/ /app/src/training/scaffolding/
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/features.py /app/src/training/features.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/sequences.py /app/src/training/sequences.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/walk_forward.py /app/src/training/walk_forward.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/training/pyfunc_wrapper.py /app/src/training/pyfunc_wrapper.py
COPY argo_pipelines/data_scientist_agent_swarm_research/src/cpcv/ /app/src/cpcv/
WORKDIR /app
ENTRYPOINT ["python", "-m", "src.training.executor"]
