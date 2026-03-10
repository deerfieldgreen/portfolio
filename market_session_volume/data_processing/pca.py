#!/usr/bin/env python3
"""
PCA Analysis Module for Market Session Volume Pipeline.

Performs comprehensive PCA analysis on OHLCV data:
- Connects to ClickHouse database
- Engineers features (MAs, RSI, Bollinger Bands, momentum indicators)
- Performs PCA with automatic component selection
- Executes feature selection (F-statistic, mutual information, Random Forest)
- Generates visualizations and logs to MLflow
- Saves artifacts for downstream steps
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

import clickhouse_connect
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectKBest, f_classif, mutual_info_classif
from sklearn.preprocessing import StandardScaler

from .logging_config import setup_logging
from .validators import validate_clickhouse_connection, validate_mlflow_connection

logger = setup_logging("pca")

# Set plot style
sns.set_style("whitegrid")


# Pair code to symbol mapping (e.g. EURUSD -> EUR_USD)
_PAIR_CODE_TO_SYMBOL = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
}


def parse_dataset_id(dataset_id: str) -> tuple[str, str] | tuple[str, str, str]:
    """
    Parse DATASET_ID into (pair, granularity) or (model_type, pair, granularity).

    Supports:
    - MODEL_PAIR_TIMEFRAME (e.g. pair_clusters_EURUSD_H1, daily_if_GBPUSD_H4)
      -> (model_type, pair, timeframe)
    - PAIR_TIMEFRAME (e.g. EURUSD_H1) -> (pair, timeframe)
    """
    if "_" not in dataset_id:
        raise ValueError(f"Invalid DATASET_ID format: {dataset_id}")

    parts = dataset_id.split("_")
    if len(parts) >= 3:
        # model_type_pair_timeframe: last part=timeframe, second-to-last + preceding=pair (6 chars)
        timeframe = parts[-1].upper()
        pair_code = parts[-2].upper()  # EURUSD, GBPUSD, USDJPY
        model_type = "_".join(parts[:-2])
        if len(pair_code) == 6:
            # Valid format
            pair = _PAIR_CODE_TO_SYMBOL.get(pair_code)
            if not pair:
                pair = pair_code[:3] + "_" + pair_code[3:]
            return (model_type, pair, timeframe)
    if len(parts) == 2:
        # pair_timeframe (e.g. EURUSD_H1)
        pair_code = parts[0].upper()
        timeframe = parts[1].upper()
        pair = _PAIR_CODE_TO_SYMBOL.get(pair_code)
        if not pair:
            pair = pair_code[:3] + "_" + pair_code[3:] if len(pair_code) == 6 else pair_code
        return (pair, timeframe)

    raise ValueError(f"Invalid DATASET_ID format: {dataset_id}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="PCA analysis for market session volume")
    parser.add_argument("--pairs", type=str, default=None,
                       help="Comma-separated list of currency pairs (overrides DATASET_ID when set)")
    parser.add_argument("--days", type=int, default=90,
                       help="Number of days of historical data to fetch")
    parser.add_argument("--granularity", type=str, default=None,
                       help="Timeframe granularity (H1, H4, D). Overrides DATASET_ID when set.")
    parser.add_argument("--n-components", type=int, default=None,
                       help="Number of PCA components (None for auto)")
    parser.add_argument("--variance-threshold", type=float, default=0.95,
                       help="Variance threshold for automatic component selection")
    parser.add_argument("--top-k-features", type=int, default=20,
                       help="Top K features to select")
    return parser.parse_args()


def get_clickhouse_config() -> Dict[str, Any]:
    """Get ClickHouse configuration from environment variables."""
    secure = os.getenv('CLICKHOUSE_SECURE', '').lower() in ('1', 'true', 'yes')
    default_port = '443' if secure else '8123'
    return {
        'host': os.getenv('CLICKHOUSE_HOST', 'localhost'),
        'port': int(os.getenv('CLICKHOUSE_PORT', default_port)),
        'username': os.environ['CLICKHOUSE_USERNAME'],
        'password': os.getenv('CLICKHOUSE_PASSWORD', ''),
        'database': os.getenv('CLICKHOUSE_DATABASE', 'oanda_data_statistics'),
        'secure': secure,
    }


def fetch_ohlcv_data(
    pairs: List[str],
    days_back: int,
    granularity: str,
    client: clickhouse_connect.driver.Client
) -> pd.DataFrame:
    """
    Fetch OHLCV data from ClickHouse.
    
    Args:
        pairs: List of currency pairs
        days_back: Number of days to fetch
        granularity: Timeframe (H1, H4, D)
        client: ClickHouse client
        
    Returns:
        DataFrame with OHLCV data
    """
    logger.info(f"Fetching {days_back} days of {granularity} data for {len(pairs)} pairs")
    
    table_name = os.getenv('OHLCV_TABLE', 'ohlcv_data')
    start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    # Format pairs for SQL IN clause
    pairs_str = "', '".join(pairs)
    
    # ohlcv_data table uses symbol, timeframe, bar_time (see oanda_data_statistics/scripts/02_create_tables.sql)
    query = f"""
    SELECT
        symbol,
        bar_time,
        open,
        high,
        low,
        close,
        volume
    FROM {table_name}
    WHERE symbol IN ('{pairs_str}')
      AND timeframe = '{granularity}'
      AND bar_time >= '{start_date}'
    ORDER BY symbol, bar_time
    """
    
    result = client.query(query)
    columns = result.column_names or ['symbol', 'bar_time', 'open', 'high', 'low', 'close', 'volume']
    df = pd.DataFrame(result.result_rows or [], columns=columns)
    df = df.rename(columns={'symbol': 'pair', 'bar_time': 'timestamp'})
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    for col in ('open', 'high', 'low', 'close', 'volume'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    logger.info(f"Fetched {len(df)} rows of OHLCV data")
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer technical indicators and features.
    
    Args:
        df: DataFrame with OHLCV data
        
    Returns:
        DataFrame with additional features
    """
    logger.info("Engineering technical features")
    
    features_df = df.copy()
    
    # Group by pair to calculate indicators per pair
    for pair in features_df['pair'].unique():
        mask = features_df['pair'] == pair
        pair_data = features_df[mask].copy()
        
        # Moving averages
        for window in [5, 10, 20, 50]:
            pair_data[f'ma_{window}'] = pair_data['close'].rolling(window=window).mean()
            pair_data[f'volume_ma_{window}'] = pair_data['volume'].rolling(window=window).mean()
        
        # RSI (Relative Strength Index)
        delta = pair_data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, 1e-10)
        pair_data['rsi'] = 100 - (100 / (1 + rs))
        
        # Bollinger Bands
        bb_window = 20
        rolling_mean = pair_data['close'].rolling(window=bb_window).mean()
        rolling_std = pair_data['close'].rolling(window=bb_window).std()
        pair_data['bb_upper'] = rolling_mean + (2 * rolling_std)
        pair_data['bb_lower'] = rolling_mean - (2 * rolling_std)
        pair_data['bb_width'] = (pair_data['bb_upper'] - pair_data['bb_lower']) / rolling_mean
        
        # Momentum indicators
        pair_data['momentum_5'] = pair_data['close'].pct_change(periods=5)
        pair_data['momentum_10'] = pair_data['close'].pct_change(periods=10)
        
        # Volatility
        pair_data['volatility'] = pair_data['close'].rolling(window=20).std()
        
        # Price range
        pair_data['price_range'] = pair_data['high'] - pair_data['low']
        pair_data['price_range_pct'] = pair_data['price_range'] / pair_data['close']
        
        # Update main dataframe
        features_df.loc[mask, pair_data.columns] = pair_data
    
    # Drop rows with NaN (from rolling calculations)
    features_df = features_df.dropna()
    
    logger.info(f"Engineered {len(features_df.columns) - 7} features, {len(features_df)} rows remain")
    return features_df


def perform_pca(
    X: np.ndarray,
    feature_names: List[str],
    n_components: int | None,
    variance_threshold: float
) -> Tuple[PCA, np.ndarray, StandardScaler]:
    """
    Perform PCA with automatic component selection.
    
    Args:
        X: Feature matrix
        feature_names: List of feature names
        n_components: Number of components (None for auto)
        variance_threshold: Variance threshold for auto selection
        
    Returns:
        Tuple of (pca_model, transformed_data, scaler)
    """
    logger.info("Performing PCA analysis")
    
    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Determine number of components
    if n_components is None:
        # Fit PCA with all components to determine optimal number
        pca_temp = PCA()
        pca_temp.fit(X_scaled)
        
        cumsum_variance = np.cumsum(pca_temp.explained_variance_ratio_)
        n_components = np.argmax(cumsum_variance >= variance_threshold) + 1
        
        logger.info(f"Auto-selected {n_components} components for {variance_threshold*100}% variance")
    
    # Fit final PCA
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X_scaled)
    
    explained_variance = pca.explained_variance_ratio_
    cumsum_variance = np.cumsum(explained_variance)
    
    logger.info(f"PCA complete: {n_components} components explain {cumsum_variance[-1]*100:.2f}% variance")
    
    return pca, X_pca, scaler


def feature_selection(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
    top_k: int
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Perform feature selection using multiple methods.
    
    Args:
        X: Feature matrix
        y: Target variable (pair indices for classification)
        feature_names: List of feature names
        top_k: Number of top features to return
        
    Returns:
        Dictionary with feature rankings from different methods
    """
    logger.info(f"Performing feature selection (top {top_k})")
    
    results = {}
    
    # F-statistic
    try:
        selector_f = SelectKBest(score_func=f_classif, k=min(top_k, len(feature_names)))
        selector_f.fit(X, y)
        
        f_scores = list(zip(feature_names, selector_f.scores_))
        f_scores_sorted = sorted(f_scores, key=lambda x: x[1], reverse=True)[:top_k]
        results['f_statistic'] = [(name, float(score)) for name, score in f_scores_sorted]
        
        logger.info(f"F-statistic selection: top feature = {f_scores_sorted[0][0]}")
    except Exception as e:
        logger.warning(f"F-statistic selection failed: {e}")
        results['f_statistic'] = []
    
    # Mutual information
    try:
        mi_scores = mutual_info_classif(X, y, random_state=42)
        mi_scores_list = list(zip(feature_names, mi_scores))
        mi_scores_sorted = sorted(mi_scores_list, key=lambda x: x[1], reverse=True)[:top_k]
        results['mutual_information'] = [(name, float(score)) for name, score in mi_scores_sorted]
        
        logger.info(f"Mutual information selection: top feature = {mi_scores_sorted[0][0]}")
    except Exception as e:
        logger.warning(f"Mutual information selection failed: {e}")
        results['mutual_information'] = []
    
    # Random Forest feature importance
    try:
        rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
        rf.fit(X, y)
        
        rf_scores = list(zip(feature_names, rf.feature_importances_))
        rf_scores_sorted = sorted(rf_scores, key=lambda x: x[1], reverse=True)[:top_k]
        results['random_forest'] = [(name, float(score)) for name, score in rf_scores_sorted]
        
        logger.info(f"Random Forest selection: top feature = {rf_scores_sorted[0][0]}")
    except Exception as e:
        logger.warning(f"Random Forest selection failed: {e}")
        results['random_forest'] = []
    
    return results


def generate_visualizations(
    pca: PCA,
    feature_names: List[str],
    feature_selection_results: Dict[str, List[Tuple[str, float]]],
    workspace_dir: str,
    dataset: str
) -> List[str]:
    """
    Generate and save PCA visualizations.
    
    Args:
        pca: Fitted PCA model
        feature_names: List of feature names
        feature_selection_results: Feature selection results
        workspace_dir: Workspace directory path
        dataset: Dataset identifier
        
    Returns:
        List of generated plot file paths
    """
    logger.info("Generating PCA visualizations")
    
    workspace = Path(workspace_dir)
    plots = []
    
    # 1. Scree plot
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        n_components = len(pca.explained_variance_ratio_)
        components = range(1, n_components + 1)
        
        ax.bar(components, pca.explained_variance_ratio_, alpha=0.7, label='Individual')
        ax.plot(components, np.cumsum(pca.explained_variance_ratio_), 'r-o', label='Cumulative')
        
        ax.set_xlabel('Principal Component')
        ax.set_ylabel('Explained Variance Ratio')
        ax.set_title(f'PCA Scree Plot - {dataset}')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        scree_path = workspace / f"{dataset}_pca_scree.png"
        plt.savefig(scree_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        plots.append(str(scree_path))
        logger.info(f"Saved scree plot to {scree_path}")
    except Exception as e:
        logger.warning(f"Failed to generate scree plot: {e}")
    
    # 2. Loadings plot (first 2 components)
    try:
        fig, ax = plt.subplots(figsize=(12, 8))
        
        loadings = pca.components_[:2].T
        
        # Plot top 15 features by magnitude
        magnitudes = np.sqrt(loadings[:, 0]**2 + loadings[:, 1]**2)
        top_indices = np.argsort(magnitudes)[-15:]
        
        for idx in top_indices:
            ax.arrow(0, 0, loadings[idx, 0], loadings[idx, 1],
                    head_width=0.02, head_length=0.02, fc='blue', ec='blue', alpha=0.6)
            ax.text(loadings[idx, 0] * 1.1, loadings[idx, 1] * 1.1,
                   feature_names[idx], fontsize=8, ha='center')
        
        ax.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)')
        ax.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)')
        ax.set_title(f'PCA Loadings (Top 15 Features) - {dataset}')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='k', linestyle='-', linewidth=0.5)
        ax.axvline(x=0, color='k', linestyle='-', linewidth=0.5)
        
        loadings_path = workspace / f"{dataset}_pca_loadings.png"
        plt.savefig(loadings_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        plots.append(str(loadings_path))
        logger.info(f"Saved loadings plot to {loadings_path}")
    except Exception as e:
        logger.warning(f"Failed to generate loadings plot: {e}")
    
    # 3. Feature importance plot
    try:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        
        for idx, (method, ax) in enumerate(zip(['f_statistic', 'mutual_information', 'random_forest'], axes)):
            if method in feature_selection_results and feature_selection_results[method]:
                features, scores = zip(*feature_selection_results[method][:10])
                
                y_pos = np.arange(len(features))
                ax.barh(y_pos, scores, alpha=0.7)
                ax.set_yticks(y_pos)
                ax.set_yticklabels(features, fontsize=8)
                ax.set_xlabel('Score')
                ax.set_title(method.replace('_', ' ').title())
                ax.grid(True, alpha=0.3, axis='x')
        
        fig.suptitle(f'Feature Selection Results - {dataset}', fontsize=14)
        plt.tight_layout()
        
        importance_path = workspace / f"{dataset}_feature_importance.png"
        plt.savefig(importance_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        plots.append(str(importance_path))
        logger.info(f"Saved feature importance plot to {importance_path}")
    except Exception as e:
        logger.warning(f"Failed to generate feature importance plot: {e}")
    
    return plots


def save_artifacts(
    pca: PCA,
    scaler: StandardScaler,
    pca_results: Dict[str, Any],
    workspace_dir: str,
    dataset: str
) -> None:
    """
    Save PCA artifacts to workspace.
    
    Args:
        pca: Fitted PCA model
        scaler: Fitted scaler
        pca_results: PCA results dictionary
        workspace_dir: Workspace directory path
        dataset: Dataset identifier
    """
    logger.info("Saving PCA artifacts")
    
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    
    # Save JSON results
    json_path = workspace / f"{dataset}_pca_results.json"
    with open(json_path, 'w') as f:
        json.dump(pca_results, f, indent=2, default=str)
    logger.info(f"Saved PCA results to {json_path}")
    
    # Save scaler
    scaler_path = workspace / f"{dataset}_scaler.pkl"
    with open(scaler_path, 'wb') as f:
        pickle.dump(scaler, f)
    logger.info(f"Saved scaler to {scaler_path}")
    
    # Save PCA model
    pca_path = workspace / f"{dataset}_pca_model.pkl"
    with open(pca_path, 'wb') as f:
        pickle.dump(pca, f)
    logger.info(f"Saved PCA model to {pca_path}")


def main():
    """Main PCA analysis workflow."""
    args = parse_args()
    
    # Get configuration
    dataset_id = os.getenv('DATASET_ID', '')
    workspace_dir = os.getenv('WORKSPACE_DIR', '/workspace')
    mlflow_tracking_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow-service:5000')
    
    # Derive pair and granularity from DATASET_ID when not in args
    if args.pairs and args.granularity:
        pairs = [p.strip() for p in args.pairs.split(',')]
        granularity = args.granularity
        dataset = dataset_id or f"MULTI_{granularity}"
    elif dataset_id:
        parsed = parse_dataset_id(dataset_id)
        if len(parsed) == 3:
            _model_type, pair, granularity = parsed
        else:
            pair, granularity = parsed
        pairs = [pair]
        dataset = dataset_id
    else:
        pairs = [p.strip() for p in (args.pairs or "EUR_USD,GBP_USD,USD_JPY").split(',')]
        granularity = args.granularity or "H1"
        dataset = dataset_id or f"MULTI_{granularity}"
    
    logger.info(f"Starting PCA analysis for dataset: {dataset}")
    logger.info(f"Workspace: {workspace_dir}")
    logger.info(f"Analyzing pairs: {pairs} (granularity: {granularity})")
    
    # Validate connections
    ch_config = get_clickhouse_config()
    validate_clickhouse_connection(ch_config)
    validate_mlflow_connection(mlflow_tracking_uri)
    
    # Set up MLflow
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    experiment_name = os.getenv('MLFLOW_EXPERIMENT', 'market-sessions-volume-analysis')
    mlflow.set_experiment(experiment_name)
    
    with mlflow.start_run(run_name=f"pca_{dataset}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"):
        # Log parameters
        mlflow.log_params({
            'dataset': dataset,
            'pairs': ','.join(pairs),
            'days_back': args.days,
            'granularity': granularity,
            'variance_threshold': args.variance_threshold,
            'top_k_features': args.top_k_features,
        })
        
        # Fetch data from ClickHouse
        ch_client = clickhouse_connect.get_client(**ch_config)
        df = fetch_ohlcv_data(pairs, args.days, granularity, ch_client)
        
        # Engineer features
        features_df = engineer_features(df)
        
        # Prepare feature matrix
        # Exclude non-feature columns
        exclude_cols = ['pair', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
        feature_cols = [col for col in features_df.columns if col not in exclude_cols]
        
        X = features_df[feature_cols].values
        feature_names = feature_cols
        
        # Create target (pair indices) for feature selection
        pair_mapping = {pair: idx for idx, pair in enumerate(features_df['pair'].unique())}
        y = features_df['pair'].map(pair_mapping).values
        
        logger.info(f"Feature matrix shape: {X.shape}")
        
        # Perform PCA
        pca, X_pca, scaler = perform_pca(
            X, feature_names,
            args.n_components,
            args.variance_threshold
        )
        
        # Feature selection
        feature_selection_results = feature_selection(X, y, feature_names, args.top_k_features)
        
        # Log metrics
        mlflow.log_metric('n_components', pca.n_components_)
        mlflow.log_metric('explained_variance_total', float(np.sum(pca.explained_variance_ratio_)))
        mlflow.log_metric('n_features_original', len(feature_names))
        mlflow.log_metric('n_samples', X.shape[0])
        
        # Log component variances
        for i, var in enumerate(pca.explained_variance_ratio_):
            mlflow.log_metric(f'explained_variance_pc{i+1}', float(var))
        
        # Generate visualizations
        plot_paths = generate_visualizations(
            pca, feature_names, feature_selection_results,
            workspace_dir, dataset
        )
        
        # Log plots to MLflow
        for plot_path in plot_paths:
            mlflow.log_artifact(plot_path)
        
        # Prepare results dictionary
        pca_results = {
            'dataset': dataset,
            'timestamp': datetime.utcnow().isoformat(),
            'n_components': int(pca.n_components_),
            'explained_variance': [float(v) for v in pca.explained_variance_ratio_],
            'cumulative_variance': [float(v) for v in np.cumsum(pca.explained_variance_ratio_)],
            'feature_names': feature_names,
            'n_samples': int(X.shape[0]),
            'pairs': pairs,
            'feature_selection': feature_selection_results,
        }
        
        # Save artifacts
        save_artifacts(pca, scaler, pca_results, workspace_dir, dataset)
        
        logger.info("✅ PCA analysis complete")


if __name__ == "__main__":
    main()
