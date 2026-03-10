"""Validation utilities for market session volume pipeline."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

import clickhouse_connect

from .logging_config import setup_logging

logger = setup_logging("validators")


def validate_pca_output(workspace_dir: str, dataset: str) -> bool:
    """
    Validate that PCA step produced all required artifacts.
    
    Args:
        workspace_dir: Path to workspace directory
        dataset: Dataset identifier (e.g., "USDJPY_H1")
        
    Returns:
        True if valid, raises exception otherwise
        
    Raises:
        FileNotFoundError: If required files are missing
        ValueError: If files are invalid
    """
    logger.info(f"Validating PCA output for dataset: {dataset}")
    
    workspace = Path(workspace_dir)
    
    # Check for required files
    required_files = [
        workspace / f"{dataset}_pca_results.json",
        workspace / f"{dataset}_scaler.pkl",
        workspace / f"{dataset}_pca_model.pkl",
    ]
    
    for file_path in required_files:
        if not file_path.exists():
            raise FileNotFoundError(f"Required PCA artifact missing: {file_path}")
        
        if file_path.stat().st_size == 0:
            raise ValueError(f"PCA artifact is empty: {file_path}")
    
    # Validate JSON structure
    pca_results_path = workspace / f"{dataset}_pca_results.json"
    try:
        with open(pca_results_path, 'r') as f:
            pca_data = json.load(f)
        
        # Check for required keys
        required_keys = ["n_components", "explained_variance", "feature_names"]
        for key in required_keys:
            if key not in pca_data:
                raise ValueError(f"PCA results missing required key: {key}")
        
        logger.info(f"✅ PCA output validation passed for {dataset}")
        return True
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in PCA results: {e}")


def validate_statistics_output(workspace_dir: str, dataset: str) -> bool:
    """
    Validate that statistics step produced valid output.
    
    Args:
        workspace_dir: Path to workspace directory
        dataset: Dataset identifier
        
    Returns:
        True if valid, raises exception otherwise
        
    Raises:
        FileNotFoundError: If statistics file is missing
        ValueError: If statistics file is invalid
    """
    logger.info(f"Validating statistics output for dataset: {dataset}")
    
    workspace = Path(workspace_dir)
    stats_file = workspace / f"{dataset}_statistics.json"
    
    if not stats_file.exists():
        raise FileNotFoundError(f"Statistics file missing: {stats_file}")
    
    if stats_file.stat().st_size == 0:
        raise ValueError(f"Statistics file is empty: {stats_file}")
    
    try:
        with open(stats_file, 'r') as f:
            stats_data = json.load(f)
        
        # Check for required keys
        required_keys = ["dataset", "sessions", "timestamp"]
        for key in required_keys:
            if key not in stats_data:
                raise ValueError(f"Statistics missing required key: {key}")
        
        logger.info(f"✅ Statistics output validation passed for {dataset}")
        return True
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in statistics file: {e}")


def validate_training_output(workspace_dir: str, dataset: str) -> bool:
    """
    Validate that training step produced model artifacts.
    
    Args:
        workspace_dir: Path to workspace directory
        dataset: Dataset identifier
        
    Returns:
        True if valid, raises exception otherwise
        
    Raises:
        FileNotFoundError: If model files are missing
        ValueError: If model files are invalid
    """
    logger.info(f"Validating training output for dataset: {dataset}")
    
    workspace = Path(workspace_dir)
    
    # Check for model files
    model_files = [
        workspace / f"{dataset}_kmeans.pkl",
        workspace / f"{dataset}_isolation_forest.pkl",
        workspace / f"{dataset}_arima.pkl",
    ]
    
    found_models = []
    for model_file in model_files:
        if model_file.exists() and model_file.stat().st_size > 0:
            found_models.append(model_file.name)
    
    if not found_models:
        raise FileNotFoundError(f"No valid model files found for {dataset}")
    
    logger.info(f"✅ Training output validation passed for {dataset} - found models: {found_models}")
    return True


def validate_clickhouse_connection(config: Dict[str, Any]) -> bool:
    """
    Validate ClickHouse database connectivity.
    
    Args:
        config: Dictionary with connection parameters
               (host, port, username, password, database)
        
    Returns:
        True if connection successful
        
    Raises:
        ConnectionError: If unable to connect after retries
    """
    logger.info(f"Validating ClickHouse connection to {config.get('host')}:{config.get('port')}")
    
    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(1, max_retries + 1):
        try:
            client = clickhouse_connect.get_client(
                host=config.get('host', 'localhost'),
                port=config.get('port', 8123),
                username=config.get('username', 'market_sessions'),
                password=config.get('password', ''),
                database=config.get('database', 'oanda_data_statistics'),
                secure=config.get('secure', False),
            )
            
            # Test connection with a simple query
            result = client.query("SELECT 1")
            
            if result:
                logger.info("✅ ClickHouse connection validation passed")
                return True
                
        except Exception as e:
            logger.warning(f"ClickHouse connection attempt {attempt}/{max_retries} failed: {e}")
            
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                raise ConnectionError(f"Failed to connect to ClickHouse after {max_retries} attempts: {e}")
    
    return False


def validate_mlflow_connection(tracking_uri: str) -> bool:
    """
    Validate MLflow tracking server connectivity.
    
    Args:
        tracking_uri: MLflow tracking URI
        
    Returns:
        True if connection successful
        
    Raises:
        ConnectionError: If unable to connect after retries
    """
    logger.info(f"Validating MLflow connection to {tracking_uri}")
    
    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(1, max_retries + 1):
        try:
            import mlflow
            from mlflow.tracking import MlflowClient
            
            mlflow.set_tracking_uri(tracking_uri)
            client = MlflowClient(tracking_uri=tracking_uri)
            
            # Test connection by listing experiments
            experiments = client.search_experiments()
            
            logger.info(f"✅ MLflow connection validation passed - found {len(experiments)} experiments")
            return True
            
        except Exception as e:
            logger.warning(f"MLflow connection attempt {attempt}/{max_retries} failed: {e}")
            
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                raise ConnectionError(f"Failed to connect to MLflow after {max_retries} attempts: {e}")
    
    return False
