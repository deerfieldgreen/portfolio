#!/usr/bin/env python3
"""
Statistics Generation Module for Market Session Volume Pipeline.

Generates session-based volume statistics from PCA outputs:
- Loads PCA-transformed data from workspace
- Computes session-based aggregations (Sydney, Tokyo, London, NY)
- Calculates volatility and volume profiles
- Validates inputs using validators
- Logs metrics to MLflow
"""
from __future__ import annotations

import json
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import mlflow
import numpy as np
import pandas as pd

from .logging_config import setup_logging
from .sessions import SESSION_HOURS
from .validators import validate_pca_output

logger = setup_logging("statistics")


def load_pca_outputs(workspace_dir: str, dataset: str) -> tuple[dict, Any, Any]:
    """
    Load PCA outputs from workspace.
    
    Args:
        workspace_dir: Workspace directory path
        dataset: Dataset identifier
        
    Returns:
        Tuple of (pca_results, pca_model, scaler)
    """
    logger.info(f"Loading PCA outputs for dataset: {dataset}")
    
    workspace = Path(workspace_dir)
    
    # Load PCA results JSON
    json_path = workspace / f"{dataset}_pca_results.json"
    with open(json_path, 'r') as f:
        pca_results = json.load(f)
    
    # Load PCA model
    pca_path = workspace / f"{dataset}_pca_model.pkl"
    with open(pca_path, 'rb') as f:
        pca_model = pickle.load(f)
    
    # Load scaler
    scaler_path = workspace / f"{dataset}_scaler.pkl"
    with open(scaler_path, 'rb') as f:
        scaler = pickle.load(f)
    
    logger.info(f"Loaded PCA outputs: {pca_results['n_components']} components")
    return pca_results, pca_model, scaler


def compute_session_statistics(pca_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute session-based volume statistics.
    
    Args:
        pca_results: PCA results dictionary
        
    Returns:
        Dictionary with session statistics
    """
    logger.info("Computing session-based statistics")
    
    # Initialize session stats
    session_stats = {}
    
    for session_name, hours in SESSION_HOURS.items():
        session_stats[session_name] = {
            'hours': hours,
            'hour_count': len(hours),
            'relative_coverage': len(hours) / 24.0,
        }
    
    # Calculate derived statistics
    stats = {
        'dataset': pca_results.get('dataset', 'unknown'),
        'timestamp': datetime.utcnow().isoformat(),
        'sessions': session_stats,
        'analysis': {
            'pca_components_used': pca_results.get('n_components', 0),
            'total_variance_explained': sum(pca_results.get('explained_variance', [])),
            'n_samples': pca_results.get('n_samples', 0),
            'pairs_analyzed': pca_results.get('pairs', []),
        },
        'session_rankings': {
            # Rank sessions by their hour coverage
            'by_coverage': sorted(
                [(name, info['hour_count']) for name, info in session_stats.items()],
                key=lambda x: x[1],
                reverse=True
            ),
        },
    }
    
    logger.info(f"Computed statistics for {len(session_stats)} sessions")
    return stats


def compute_volatility_profiles(pca_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute volatility profiles based on PCA variance.
    
    Args:
        pca_results: PCA results dictionary
        
    Returns:
        Dictionary with volatility profiles
    """
    logger.info("Computing volatility profiles")
    
    explained_variance = pca_results.get('explained_variance', [])
    
    profiles = {
        'variance_distribution': {
            f'pc_{i+1}': float(var) for i, var in enumerate(explained_variance)
        },
        'high_variance_components': [
            i + 1 for i, var in enumerate(explained_variance) if var > 0.1
        ],
        'low_variance_components': [
            i + 1 for i, var in enumerate(explained_variance) if var < 0.05
        ],
    }
    
    logger.info(f"High variance components: {profiles['high_variance_components']}")
    return profiles


def compute_volume_profiles(pca_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute volume profiles per pair.
    
    Args:
        pca_results: PCA results dictionary
        
    Returns:
        Dictionary with volume profiles
    """
    logger.info("Computing volume profiles")
    
    pairs = pca_results.get('pairs', [])
    
    # Create basic volume profile structure
    profiles = {
        'pairs': pairs,
        'pair_count': len(pairs),
        'profile_type': 'normalized',
    }
    
    # Get top features related to volume
    feature_selection = pca_results.get('feature_selection', {})
    volume_features = []
    
    for method_results in feature_selection.values():
        for feature_name, score in method_results:
            if 'volume' in feature_name.lower():
                volume_features.append((feature_name, score))
    
    profiles['top_volume_features'] = volume_features[:10]
    
    logger.info(f"Computed volume profiles for {len(pairs)} pairs")
    return profiles


def save_statistics(statistics: Dict[str, Any], workspace_dir: str, dataset: str) -> None:
    """
    Save statistics to workspace.
    
    Args:
        statistics: Statistics dictionary
        workspace_dir: Workspace directory path
        dataset: Dataset identifier
    """
    logger.info("Saving statistics")
    
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    
    stats_path = workspace / f"{dataset}_statistics.json"
    with open(stats_path, 'w') as f:
        json.dump(statistics, f, indent=2, default=str)
    
    logger.info(f"Saved statistics to {stats_path}")


def log_to_mlflow(statistics: Dict[str, Any]) -> None:
    """
    Log statistics metrics to MLflow.
    
    Args:
        statistics: Statistics dictionary
    """
    logger.info("Logging statistics to MLflow")
    
    # Log basic metrics
    analysis = statistics.get('analysis', {})
    mlflow.log_metric('pca_components_used', analysis.get('pca_components_used', 0))
    mlflow.log_metric('total_variance_explained', analysis.get('total_variance_explained', 0))
    mlflow.log_metric('n_samples', analysis.get('n_samples', 0))
    mlflow.log_metric('n_pairs_analyzed', len(analysis.get('pairs_analyzed', [])))
    
    # Log session counts
    sessions = statistics.get('sessions', {})
    for session_name, session_info in sessions.items():
        mlflow.log_metric(f'session_{session_name}_hours', session_info['hour_count'])
        mlflow.log_metric(f'session_{session_name}_coverage', session_info['relative_coverage'])
    
    # Log volatility metrics
    volatility = statistics.get('volatility_profiles', {})
    if volatility:
        mlflow.log_metric('n_high_variance_components', len(volatility.get('high_variance_components', [])))
        mlflow.log_metric('n_low_variance_components', len(volatility.get('low_variance_components', [])))
    
    # Log volume metrics
    volume = statistics.get('volume_profiles', {})
    if volume:
        mlflow.log_metric('n_pairs_profiled', volume.get('pair_count', 0))
    
    logger.info("✅ Statistics logged to MLflow")


def main():
    """Main statistics generation workflow."""
    dataset = os.getenv('DATASET_ID', 'UNKNOWN')
    workspace_dir = os.getenv('WORKSPACE_DIR', '/workspace')
    mlflow_tracking_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow-service:5000')
    
    logger.info(f"Starting statistics generation for dataset: {dataset}")
    logger.info(f"Workspace: {workspace_dir}")
    
    # Validate PCA outputs exist
    try:
        validate_pca_output(workspace_dir, dataset)
    except Exception as e:
        logger.error(f"PCA output validation failed: {e}")
        raise
    
    # Set up MLflow
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    experiment_name = os.getenv('MLFLOW_EXPERIMENT', 'market-sessions-volume-analysis')
    mlflow.set_experiment(experiment_name)
    
    with mlflow.start_run(run_name=f"statistics_{dataset}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"):
        # Log parameters
        mlflow.log_param('dataset', dataset)
        mlflow.log_param('workspace_dir', workspace_dir)
        
        # Load PCA outputs
        pca_results, pca_model, scaler = load_pca_outputs(workspace_dir, dataset)
        
        # Compute statistics
        session_stats = compute_session_statistics(pca_results)
        volatility_profiles = compute_volatility_profiles(pca_results)
        volume_profiles = compute_volume_profiles(pca_results)
        
        # Combine all statistics
        statistics = session_stats
        statistics['volatility_profiles'] = volatility_profiles
        statistics['volume_profiles'] = volume_profiles
        
        # Save statistics
        save_statistics(statistics, workspace_dir, dataset)
        
        # Log to MLflow
        log_to_mlflow(statistics)
        
        # Log statistics file as artifact
        stats_path = Path(workspace_dir) / f"{dataset}_statistics.json"
        mlflow.log_artifact(str(stats_path))
        
        logger.info("✅ Statistics generation complete")


if __name__ == "__main__":
    main()
