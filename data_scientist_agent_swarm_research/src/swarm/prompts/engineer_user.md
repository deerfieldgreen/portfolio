Generate a complete experiment.py for the following ExperimentSpec:

{experiment_spec_json}

The code will run inside a container with:
- PyTorch (GPU available), numpy, pandas, scikit-learn, XGBoost, Optuna
- Scaffolding: src.training.scaffolding.{{data_loader, training_loop, metrics, mlflow_log}}
- Data at /workspace/data.parquet
- Write run_id to /tmp/run_id

Output ONLY the Python code, wrapped in ```python blocks.
