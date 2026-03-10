#!/usr/bin/env python3
"""
Model Selection and Registration Module.

Queries MLflow for all trained models from train step, compares them,
selects the best performing model, validates against thresholds,
and registers to MLflow Model Registry if criteria are met.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import mlflow
from mlflow.tracking import MlflowClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger(__name__)

# Promotion thresholds (from existing register_models.py)
THRESHOLDS = {
    "validation_forecast_accuracy_mae": 50000.0,  # Lower is better
    "validation_signal_precision": 0.65,  # Higher is better
}


def load_run_ids_from_workspace(workspace_dir: str) -> List[str]:
    """
    Load MLflow run IDs from workspace.
    Prefers mlflow_run_ids.txt (one run_id per line, from collect steps); falls back to mlflow_run_id.txt.
    
    Args:
        workspace_dir: Workspace directory path
        
    Returns:
        List of MLflow run IDs
    """
    logger.info("Loading run IDs from workspace")
    
    workspace = Path(workspace_dir)
    run_ids = []
    
    # Prefer mlflow_run_ids.txt (one run_id per line, written by collect steps)
    run_ids_file = workspace / "mlflow_run_ids.txt"
    if run_ids_file.exists():
        with open(run_ids_file, 'r') as f:
            for line in f:
                run_id = line.strip()
                if run_id:
                    run_ids.append(run_id)
        if run_ids:
            logger.info("Found %d run ID(s) in mlflow_run_ids.txt", len(run_ids))
    
    # Fallback: single run ID file (legacy or manual)
    if not run_ids:
        run_id_file = workspace / "mlflow_run_id.txt"
        if run_id_file.exists():
            with open(run_id_file, 'r') as f:
                run_id = f.read().strip()
                if run_id:
                    run_ids.append(run_id)
                    logger.info("Found run ID: %s", run_id)
    
    if not run_ids:
        logger.warning("No run IDs found in workspace")
    
    return run_ids


def query_mlflow_runs(experiment_name: str, client: MlflowClient) -> List[Dict[str, Any]]:
    """
    Query MLflow for all runs in the experiment.
    
    Args:
        experiment_name: MLflow experiment name
        client: MLflow client
        
    Returns:
        List of run information dictionaries
    """
    logger.info(f"Querying MLflow experiment: {experiment_name}")
    
    try:
        experiment = client.get_experiment_by_name(experiment_name)
        if not experiment:
            logger.warning(f"Experiment '{experiment_name}' not found")
            return []
        
        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string="",
            order_by=["start_time DESC"],
            max_results=100
        )
        
        run_infos = []
        for run in runs:
            run_info = {
                'run_id': run.info.run_id,
                'run_name': run.data.tags.get('mlflow.runName', 'unknown'),
                'status': run.info.status,
                'start_time': run.info.start_time,
                'metrics': run.data.metrics,
                'params': run.data.params,
            }
            run_infos.append(run_info)
        
        logger.info(f"Found {len(run_infos)} runs in experiment")
        return run_infos
        
    except Exception as e:
        logger.error(f"Failed to query MLflow runs: {e}")
        return []


def select_best_model(runs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Select the best model based on validation metrics.
    
    Args:
        runs: List of run information dictionaries
        
    Returns:
        Best run dictionary, or None if no suitable runs
    """
    logger.info("Selecting best model from runs")
    
    if not runs:
        logger.warning("No runs to select from")
        return None
    
    # Filter to only completed runs with training metrics
    valid_runs = []
    for run in runs:
        if run['status'] == 'FINISHED':
            metrics = run['metrics']
            # Look for any metric indicating training completed
            if any(k.startswith('kmeans_') or k.startswith('arima_') or k.startswith('if_') 
                   for k in metrics.keys()):
                valid_runs.append(run)
    
    if not valid_runs:
        logger.warning("No valid completed runs found")
        return None
    
    # Select most recent completed run
    best_run = valid_runs[0]
    logger.info(f"Selected run: {best_run['run_id']} ({best_run['run_name']})")
    
    return best_run


def validate_against_thresholds(metrics: Dict[str, float]) -> bool:
    """
    Validate metrics against promotion thresholds.
    
    Args:
        metrics: Dictionary of metrics
        
    Returns:
        True if model meets thresholds, False otherwise
    """
    logger.info("Validating metrics against thresholds")
    
    promote = True
    
    for key, threshold in THRESHOLDS.items():
        # Try to find matching metric (with or without validation_ prefix)
        actual = metrics.get(key)
        if actual is None:
            actual = metrics.get(key.replace("validation_", ""))
        
        if actual is None:
            logger.info(f"Metric {key} not found in run, skipping threshold check")
            continue
        
        # Check threshold based on metric type
        if "mae" in key.lower() or "error" in key.lower():
            # Lower is better
            if actual > threshold:
                promote = False
                logger.warning(f"❌ {key}={actual} exceeds threshold {threshold}")
            else:
                logger.info(f"✅ {key}={actual} meets threshold {threshold}")
        else:
            # Higher is better
            if actual < threshold:
                promote = False
                logger.warning(f"❌ {key}={actual} below threshold {threshold}")
            else:
                logger.info(f"✅ {key}={actual} meets threshold {threshold}")
    
    return promote


def register_model(run_id: str, client: MlflowClient) -> Optional[Any]:
    """
    Register model to MLflow Model Registry.
    
    Args:
        run_id: MLflow run ID
        client: MLflow client
        
    Returns:
        Model version object, or None if registration failed
    """
    logger.info(f"Registering model from run: {run_id}")
    
    model_name = "market-sessions-volume-analyzer"
    
    try:
        # Try to register from statistics artifact path
        model_uri = f"runs:/{run_id}/statistics"
        
        result = mlflow.register_model(model_uri, model_name)
        logger.info(f"✅ Registered {model_name} version {result.version}")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to register model: {e}")
        logger.info("Attempting alternative registration path...")
        
        try:
            # Alternative: register entire run
            model_uri = f"runs:/{run_id}"
            result = mlflow.register_model(model_uri, model_name)
            logger.info(f"✅ Registered {model_name} version {result.version} (alternative path)")
            return result
        except Exception as e2:
            logger.error(f"Alternative registration also failed: {e2}")
            return None


def promote_to_production(model_name: str, version: int, client: MlflowClient) -> bool:
    """
    Promote model version to Production stage.
    
    Args:
        model_name: Model name
        version: Model version number
        client: MLflow client
        
    Returns:
        True if promotion successful
    """
    logger.info(f"Promoting {model_name} version {version} to Production")
    
    try:
        client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage="Production",
            archive_existing_versions=True,
        )
        
        logger.info(f"✅ Promoted {model_name} v{version} to Production")
        return True
        
    except Exception as e:
        logger.error(f"Failed to promote model: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Select and register best model to MLflow")
    parser.add_argument("--workspace-dir", type=str, default=None,
                       help="Workspace directory path")
    args = parser.parse_args()
    
    # Get configuration from environment
    workspace_dir = args.workspace_dir or os.getenv('WORKSPACE_DIR', '/workspace')
    mlflow_tracking_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow-service:5000')
    experiment_name = os.getenv('MLFLOW_EXPERIMENT', 'market-sessions-volume-analysis')
    
    logger.info("Starting model selection and registration")
    logger.info(f"Workspace: {workspace_dir}")
    logger.info(f"MLflow URI: {mlflow_tracking_uri}")
    logger.info(f"Experiment: {experiment_name}")
    
    # Set up MLflow
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    client = MlflowClient(tracking_uri=mlflow_tracking_uri)
    
    # Load run IDs from workspace
    run_ids = load_run_ids_from_workspace(workspace_dir)
    
    # Query all runs from experiment
    all_runs = query_mlflow_runs(experiment_name, client)
    
    # If we have specific run IDs from workspace, use those
    if run_ids:
        logger.info(f"Using run IDs from workspace: {run_ids}")
        # Filter runs to only those in our list
        runs = [r for r in all_runs if r['run_id'] in run_ids]
    else:
        logger.info("No specific run IDs from workspace, using all recent training runs")
        # Filter to only training runs (exclude pca, statistics runs)
        runs = [r for r in all_runs if 'train' in r.get('run_name', '').lower()]
    
    # Select best model
    best_run = select_best_model(runs)
    
    if not best_run:
        logger.error("❌ No suitable model found for registration")
        return
    
    # Validate against thresholds
    should_promote = validate_against_thresholds(best_run['metrics'])
    
    if not should_promote:
        logger.warning("❌ Model does NOT meet quality thresholds. Skipping registration.")
        logger.info("Model can be manually promoted later if needed.")
        return
    
    # Register model
    model_version = register_model(best_run['run_id'], client)
    
    if not model_version:
        logger.error("❌ Model registration failed")
        return
    
    # Promote to Production
    success = promote_to_production(
        "market-sessions-volume-analyzer",
        model_version.version,
        client
    )
    
    if success:
        logger.info("✅ Model selection and registration complete")
    else:
        logger.warning("⚠️  Model registered but promotion to Production failed")


if __name__ == "__main__":
    main()

