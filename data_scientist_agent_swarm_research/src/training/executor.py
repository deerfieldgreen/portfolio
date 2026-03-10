"""
Generic experiment executor. Receives experiment code via S3 artifact.
The code is written to /workspace/experiment.py by Argo.
"""
import os, sys, importlib.util, traceback
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import mlflow

def main():
    code_path = os.environ.get("EXPERIMENT_CODE_PATH", "/workspace/experiment.py")

    if not os.path.exists(code_path):
        print(f"FATAL: experiment code not found at {code_path}")
        sys.exit(1)

    # Load the experiment module dynamically
    spec = importlib.util.spec_from_file_location("experiment", code_path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"FATAL: failed to load experiment code: {e}")
        traceback.print_exc()
        sys.exit(1)

    # The experiment module must define run_experiment()
    if not hasattr(module, "run_experiment"):
        print("FATAL: experiment.py must define run_experiment()")
        sys.exit(1)

    try:
        module.run_experiment()
    except Exception as e:
        # Log failure to MLflow so the swarm can learn from it
        with mlflow.start_run():
            mlflow.log_param("status", "crash")
            mlflow.log_param("error", str(e)[:500])
            mlflow.log_param("traceback", traceback.format_exc()[:2000])
        print(f"Experiment failed: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
