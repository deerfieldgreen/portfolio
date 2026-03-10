# src/swarm/hera_submit.py

import json, time, uuid, boto3
from hera.workflows import (
    Workflow, DAG, Task, Container, Parameter,
    Artifact, S3Artifact, models as m,
)
from src.shared.config import SharedConfig

cfg = SharedConfig()

REGISTRY = "registry.digitalocean.com/ams3-digitalocean-cervid-registry"


def submit_swarm_cycle(
    cycle_id: str,
    experiments: list,
    generated_code: dict,
) -> str:
    """
    Build and submit an Argo Workflow for one swarm cycle.
    Returns: Argo workflow name (for polling)
    """
    s3 = boto3.client(
        "s3",
        endpoint_url=cfg.MLFLOW_S3_ENDPOINT_URL,
        aws_access_key_id=cfg.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=cfg.AWS_SECRET_ACCESS_KEY,
    )

    code_s3_keys = {}
    for exp_id, code in generated_code.items():
        key = f"fx-swarm/cycles/{cycle_id}/{exp_id}/experiment.py"
        s3.put_object(
            Bucket=cfg.S3_ARTIFACT_BUCKET,
            Key=key,
            Body=code.encode("utf-8"),
        )
        code_s3_keys[exp_id] = key

    from collections import defaultdict
    data_groups = defaultdict(list)
    for exp in experiments:
        data_groups[(exp["pair"], exp["timeframe"])].append(exp)

    with Workflow(
        generate_name=f"swarm-cycle-{cycle_id}-",
        namespace=cfg.ARGO_NAMESPACE,
        entrypoint="cycle-dag",
        artifact_gc=m.ArtifactGC(strategy="OnWorkflowDeletion"),
    ) as wf:

        with DAG(name="cycle-dag") as dag:
            extract_tasks = {}
            for (pair, tf), group_exps in data_groups.items():
                extract_name = f"extract-{pair}-{tf}".lower().replace("_", "-")
                extract_task = Task(
                    name=extract_name,
                    template="extract-data-template",
                    arguments=[
                        Parameter(name="pair", value=pair),
                        Parameter(name="timeframe", value=tf),
                    ],
                )
                extract_tasks[(pair, tf)] = extract_task

            train_tasks = {}
            for exp in experiments:
                exp_id = exp["experiment_id"]
                pair_tf = (exp["pair"], exp["timeframe"])
                train_name = f"train-{exp_id[:8]}".lower()

                train_task = Task(
                    name=train_name,
                    template="train-template",
                    dependencies=[extract_tasks[pair_tf].name],
                    arguments=[
                        Parameter(name="experiment_id", value=exp_id),
                        Parameter(name="pair", value=exp["pair"]),
                        Parameter(name="timeframe", value=exp["timeframe"]),
                        Parameter(name="code_s3_key", value=code_s3_keys[exp_id]),
                        Artifact(
                            name="training-data",
                            from_=f"{{{{tasks.{extract_tasks[pair_tf].name}.outputs.artifacts.training-data}}}}",
                        ),
                    ],
                )
                train_tasks[exp_id] = train_task

            eval_tasks = {}
            for exp in experiments:
                exp_id = exp["experiment_id"]
                eval_name = f"eval-{exp_id[:8]}".lower()

                eval_task = Task(
                    name=eval_name,
                    template="evaluate-template",
                    dependencies=[train_tasks[exp_id].name],
                    arguments=[
                        Parameter(name="experiment_id", value=exp_id),
                        Parameter(name="pair", value=exp["pair"]),
                        Parameter(name="timeframe", value=exp["timeframe"]),
                        Parameter(
                            name="run_id",
                            value=f"{{{{tasks.{train_tasks[exp_id].name}.outputs.parameters.run_id}}}}",
                        ),
                    ],
                )
                eval_tasks[exp_id] = eval_task

        _add_extract_template(wf)
        _add_train_template(wf)
        _add_evaluate_template(wf)

    wf.create()
    return wf.name


def _add_extract_template(wf):
    """CPU pod: queries ClickHouse, outputs .parquet as S3 artifact."""
    wf.templates.append(m.Template(
        name="extract-data-template",
        inputs=m.Inputs(parameters=[
            m.Parameter(name="pair"),
            m.Parameter(name="timeframe"),
        ]),
        outputs=m.Outputs(artifacts=[
            m.Artifact(
                name="training-data",
                path="/workspace/data.parquet",
            ),
        ]),
        node_selector={
            "doks.digitalocean.com/node-pool": cfg.CPU_NODE_POOL,
        },
        container=m.Container(
            image=f"{REGISTRY}/fx-ops:latest",
            command=["python", "-m", "src.training.extract_training_data"],
            env=[
                m.EnvVar(name="PAIR", value="{{inputs.parameters.pair}}"),
                m.EnvVar(name="TIMEFRAME", value="{{inputs.parameters.timeframe}}"),
            ],
            env_from=[m.EnvFromSource(secret_ref=m.SecretEnvSource(name="argo-data-science-swarm"))],
            resources=m.ResourceRequirements(
                requests={"cpu": "1", "memory": "4Gi"},
                limits={"cpu": "2", "memory": "8Gi"},
            ),
            volume_mounts=[m.VolumeMount(name="workspace", mount_path="/workspace")],
        ),
        volumes=[m.Volume(name="workspace", empty_dir=m.EmptyDirVolumeSource(size_limit="2Gi"))],
    ))


def _add_train_template(wf):
    """GPU pod: generic executor, loads experiment code from S3 artifact."""
    wf.templates.append(m.Template(
        name="train-template",
        inputs=m.Inputs(
            parameters=[
                m.Parameter(name="experiment_id"),
                m.Parameter(name="pair"),
                m.Parameter(name="timeframe"),
                m.Parameter(name="code_s3_key"),
            ],
            artifacts=[
                m.Artifact(name="training-data", path="/workspace/data.parquet"),
                m.Artifact(
                    name="experiment-code",
                    path="/workspace/experiment.py",
                    s3=m.S3Artifact(
                        key="{{inputs.parameters.code_s3_key}}",
                    ),
                ),
            ],
        ),
        outputs=m.Outputs(parameters=[
            m.Parameter(name="run_id", value_from=m.ValueFrom(path="/tmp/run_id")),
        ]),
        node_selector={
            "doks.digitalocean.com/node-pool": cfg.GPU_NODE_POOL,
        },
        active_deadline_seconds=7200,
        container=m.Container(
            image=f"{REGISTRY}/fx-training:latest",
            env=[
                m.EnvVar(name="EXPERIMENT_CODE_PATH", value="/workspace/experiment.py"),
                m.EnvVar(name="PAIR", value="{{inputs.parameters.pair}}"),
                m.EnvVar(name="TIMEFRAME", value="{{inputs.parameters.timeframe}}"),
                m.EnvVar(name="EXPERIMENT_ID", value="{{inputs.parameters.experiment_id}}"),
                m.EnvVar(name="OPENBLAS_NUM_THREADS", value="1"),
                m.EnvVar(name="OMP_NUM_THREADS", value="1"),
                m.EnvVar(name="MKL_NUM_THREADS", value="1"),
            ],
            env_from=[m.EnvFromSource(secret_ref=m.SecretEnvSource(name="argo-data-science-swarm"))],
            resources=m.ResourceRequirements(
                requests={"memory": "8Gi"},
                limits={"nvidia.com/gpu": "1", "memory": "16Gi"},
            ),
            volume_mounts=[m.VolumeMount(name="workspace", mount_path="/workspace")],
        ),
        volumes=[m.Volume(name="workspace", empty_dir=m.EmptyDirVolumeSource(size_limit="5Gi"))],
    ))


def _add_evaluate_template(wf):
    """CPU pod: CPCV evaluation, deterministic."""
    wf.templates.append(m.Template(
        name="evaluate-template",
        inputs=m.Inputs(parameters=[
            m.Parameter(name="experiment_id"),
            m.Parameter(name="pair"),
            m.Parameter(name="timeframe"),
            m.Parameter(name="run_id"),
        ]),
        outputs=m.Outputs(parameters=[
            m.Parameter(name="eval_result", value_from=m.ValueFrom(path="/tmp/eval_result.json")),
        ]),
        node_selector={
            "doks.digitalocean.com/node-pool": cfg.CPU_NODE_POOL,
        },
        container=m.Container(
            image=f"{REGISTRY}/fx-ops:latest",
            command=["python", "-m", "src.swarm.evaluator"],
            env=[
                m.EnvVar(name="RUN_ID", value="{{inputs.parameters.run_id}}"),
                m.EnvVar(name="PAIR", value="{{inputs.parameters.pair}}"),
                m.EnvVar(name="TIMEFRAME", value="{{inputs.parameters.timeframe}}"),
                m.EnvVar(name="EXPERIMENT_ID", value="{{inputs.parameters.experiment_id}}"),
            ],
            env_from=[m.EnvFromSource(secret_ref=m.SecretEnvSource(name="argo-data-science-swarm"))],
            resources=m.ResourceRequirements(
                requests={"cpu": "2", "memory": "4Gi"},
                limits={"cpu": "4", "memory": "8Gi"},
            ),
        ),
    ))


def poll_workflow(workflow_name: str, timeout_sec: int = 14400) -> dict:
    """Poll Argo workflow until completion. Returns final status + per-task outputs."""
    from hera.workflows import WorkflowsService
    service = WorkflowsService()
    start = time.time()

    while time.time() - start < timeout_sec:
        wf = service.get_workflow(workflow_name, namespace=cfg.ARGO_NAMESPACE)
        phase = wf.status.phase if wf.status else None

        if phase in ("Succeeded", "Failed", "Error"):
            return {
                "phase": phase,
                "nodes": {
                    name: {
                        "phase": node.phase,
                        "outputs": node.outputs.dict() if node.outputs else {},
                    }
                    for name, node in (wf.status.nodes or {}).items()
                },
            }

        time.sleep(30)

    return {"phase": "Timeout", "nodes": {}}
