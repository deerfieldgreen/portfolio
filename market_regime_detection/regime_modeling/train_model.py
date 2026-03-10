"""
Regime modeling module using HMM and GARCH.
Trains Hidden Markov Models to detect market regimes and GARCH models for volatility,
then logs results to ClickHouse.
"""

import json
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional
from datetime import datetime

import pandas as pd
import numpy as np
import yaml
import clickhouse_connect

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None) -> Dict:
    """Load configuration from YAML file. Tries config.yaml (container) then ../config.yaml (local)."""
    base = Path(__file__).parent
    candidates = (config_path,) if config_path else ("config.yaml", "../config.yaml")
    config_file = None
    for c in candidates:
        p = (base / c).resolve()
        if p.exists():
            config_file = p
            break
    if config_file is None:
        config_file = base / (config_path or "config.yaml")
    if not config_file.exists():
        config_yaml = os.environ.get("CONFIG_YAML", "")
        if config_yaml:
            return yaml.safe_load(config_yaml)
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def get_clickhouse_client(config: Dict):
    """Get ClickHouse client from configuration and environment."""
    host = os.environ.get("CLICKHOUSE_HOST")
    port = int(os.environ.get("CLICKHOUSE_PORT", 8123))
    username = os.environ["CLICKHOUSE_USERNAME"]
    password = os.environ.get("CLICKHOUSE_PASSWORD", "")
    database = os.environ["CLICKHOUSE_DATABASE"]
    secure = os.environ.get("CLICKHOUSE_SECURE", "").lower() in ("true", "1", "yes")

    if not host:
        raise ValueError("CLICKHOUSE_HOST environment variable required")

    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=username,
        password=password,
        database=database,
        secure=secure
    )


def _fetch_previous_hmm_params(config: Dict, pair: str, timeframe: str) -> Optional[Dict]:
    """Fetch previous HMM parameters from ClickHouse for warm-starting."""
    try:
        client = get_clickhouse_client(config)
        query = """
        SELECT hmm_params
        FROM mr_transition_matrices
        WHERE pair = {pair:String} AND timeframe = {timeframe:String}
          AND hmm_params != ''
        ORDER BY timestamp DESC
        LIMIT 1
        """
        result = client.query(query, parameters={"pair": pair, "timeframe": timeframe})
        if result.result_rows and result.result_rows[0][0]:
            return json.loads(result.result_rows[0][0])
    except Exception as e:
        logger.warning(f"Failed to fetch previous HMM params: {e}")
    return None


def train_hmm_model(features: np.ndarray, config: Dict, previous_params: Optional[Dict] = None):
    """
    Train Hidden Markov Model on features.

    Args:
        features: Feature matrix (n_samples, n_features)
        config: Configuration dictionary
        previous_params: Optional previous HMM parameters for warm-starting

    Returns:
        Trained HMM model
    """
    try:
        from hmmlearn import hmm
    except ImportError:
        logger.error("hmmlearn not installed, using mock model")
        return None

    hmm_config = config.get("hmm", {})
    n_states = hmm_config.get("n_states", 3)
    covariance_type = hmm_config.get("covariance_type", "full")
    n_iter = hmm_config.get("n_iter", 500)
    tol = hmm_config.get("tol", 0.01)
    random_state = hmm_config.get("random_state", 42)

    # Warm-start from previous parameters if available and feature dimensions match
    warm_start = False
    if (previous_params
            and previous_params.get("n_features") == features.shape[1]
            and previous_params.get("n_states") == n_states):
        try:
            model = hmm.GaussianHMM(
                n_components=n_states,
                covariance_type=covariance_type,
                n_iter=n_iter,
                tol=tol,
                random_state=random_state,
                verbose=False,
                init_params="",
                params="stmc",
            )
            model.startprob_ = np.array(previous_params["startprob"])
            model.transmat_ = np.array(previous_params["transmat"])
            model.means_ = np.array(previous_params["means"])
            model.covars_ = np.array(previous_params["covars"])
            warm_start = True
            logger.info("Warm-starting HMM from previous parameters")
        except Exception as e:
            logger.warning(f"Failed to warm-start HMM: {e}. Falling back to random init.")
            warm_start = False

    if not warm_start:
        model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type=covariance_type,
            n_iter=n_iter,
            tol=tol,
            random_state=random_state,
            verbose=False
        )

    logger.info(f"Training HMM with {n_states} states (warm_start={warm_start})")

    try:
        model.fit(features)
        logger.info(f"HMM trained successfully, converged: {model.monitor_.converged}")
        return model
    except Exception as e:
        logger.error(f"HMM training failed: {e}")
        return None


def predict_regimes(model, features: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Predict regime states and probabilities.

    Args:
        model: Trained HMM model
        features: Feature matrix

    Returns:
        states: Array of regime states (n_samples,)
        probabilities: Array of state probabilities (n_samples, n_states)

    Raises:
        RuntimeError: If model is None (hmmlearn unavailable or training failed).
    """
    if model is None:
        raise RuntimeError(
            "HMM model is None (hmmlearn unavailable or training failed). "
            "Aborting to prevent invalid data from being written to ClickHouse."
        )

    try:
        # Use Viterbi algorithm to find most likely sequence
        states = model.predict(features)
        # Get posterior probabilities
        probabilities = model.predict_proba(features)
        return states, probabilities
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        n_samples = len(features)
        n_states = model.n_components
        states = np.zeros(n_samples, dtype=int)
        probabilities = np.zeros((n_samples, n_states))
        probabilities[:, 0] = 1.0
        return states, probabilities


def compute_model_metrics(model, features: np.ndarray) -> Dict:
    """
    Compute model quality metrics.

    Args:
        model: Trained HMM model
        features: Feature matrix

    Returns:
        Dictionary with metrics (log_likelihood, aic, bic)

    Raises:
        RuntimeError: If model is None.
    """
    if model is None:
        raise RuntimeError(
            "HMM model is None. Cannot compute metrics without a trained model."
        )

    try:
        # Log likelihood
        log_likelihood = model.score(features)

        # Number of parameters
        n_states = model.n_components
        n_features = features.shape[1]

        # For full covariance: means + covariances + transition matrix
        if model.covariance_type == "full":
            n_params = n_states * n_features  # means
            n_params += n_states * n_features * (n_features + 1) / 2  # covariances
            n_params += n_states * (n_states - 1)  # transitions
        else:
            n_params = n_states * n_features * 2 + n_states * (n_states - 1)

        n_samples = len(features)

        # AIC = 2k - 2ln(L)
        aic = 2 * n_params - 2 * log_likelihood

        # BIC = k*ln(n) - 2ln(L)
        bic = n_params * np.log(n_samples) - 2 * log_likelihood

        return {
            "log_likelihood": float(log_likelihood),
            "aic": float(aic),
            "bic": float(bic)
        }
    except Exception as e:
        logger.error(f"Metric computation failed: {e}")
        raise


def fit_garch_model(returns: pd.Series, config: Dict):
    """
    Fit GARCH model to returns.

    Args:
        returns: Log returns series
        config: Configuration dictionary

    Returns:
        Tuple of (fitted result, conditional_volatility Series) or (None, None) on failure.
    """
    try:
        from arch import arch_model
    except ImportError:
        logger.warning("arch library not installed, skipping GARCH")
        return None, None

    garch_config = config.get("garch", {})
    p = garch_config.get("p", 1)
    q = garch_config.get("q", 1)
    vol = garch_config.get("vol", "GARCH")
    dist = garch_config.get("dist", "normal")

    logger.info(f"Fitting GARCH({p},{q}) model")

    try:
        # Scale returns to percentage for numerical stability
        returns_scaled = returns * 100

        model = arch_model(
            returns_scaled,
            vol=vol,
            p=p,
            q=q,
            dist=dist,
            rescale=False
        )

        result = model.fit(disp="off")
        cond_vol = result.conditional_volatility
        logger.info("GARCH model fitted successfully")
        return result, cond_vol
    except Exception as e:
        logger.error(f"GARCH fitting failed: {e}")
        return None, None


def compute_confidence_score(probabilities: np.ndarray, config: Dict) -> np.ndarray:
    """
    Compute confidence scores based on state probabilities.

    Args:
        probabilities: State probabilities (n_samples, n_states)
        config: Configuration dictionary

    Returns:
        Confidence scores (n_samples,)
    """
    # Confidence is the maximum probability across states
    max_probs = probabilities.max(axis=1)
    return max_probs


def detect_regime_changes(states: np.ndarray) -> np.ndarray:
    """
    Detect regime changes.

    Args:
        states: Array of regime states

    Returns:
        Binary array where 1 indicates a regime change
    """
    changes = np.zeros(len(states), dtype=int)
    changes[1:] = (states[1:] != states[:-1]).astype(int)
    return changes


def compute_regime_duration(states: np.ndarray) -> np.ndarray:
    """
    Compute duration in current regime.

    Args:
        states: Array of regime states

    Returns:
        Array of durations (periods in current regime)
    """
    durations = np.zeros(len(states), dtype=int)
    current_duration = 0
    current_state = None

    for i, state in enumerate(states):
        if state != current_state:
            current_duration = 1
            current_state = state
        else:
            current_duration += 1
        durations[i] = current_duration

    return durations


def log_to_clickhouse(df: pd.DataFrame, model, metrics: Dict, emission_params: Dict, config: Dict,
                      garch_cond_vol: pd.Series | None = None):
    """
    Log regime detection results to ClickHouse.

    Args:
        df: DataFrame with features and predictions
        model: Trained HMM model
        metrics: Model quality metrics
        emission_params: Emission parameters per state
        config: Configuration dictionary
        garch_cond_vol: Optional GARCH conditional volatility series (percentage-scaled)
    """
    try:
        client = get_clickhouse_client(config)
        table = config.get("clickhouse", {}).get("tables", {}).get("regimes", "mr_regime_states")

        # Prepare data for insertion
        insert_data = df[[
            "timestamp", "pair", "timeframe", "regime_state",
            "log_return", "volatility", "rsi", "macd", "atr",
            "confidence_score", "regime_duration", "regime_change"
        ]].copy()

        # Add state probabilities as arrays
        n_states = model.n_components if model else 3
        for i in range(n_states):
            insert_data[f"state_prob_{i}"] = df["state_probabilities"].apply(lambda x: x[i])

        # Add emission parameters as arrays
        insert_data["mean_returns_per_state"] = [emission_params["mean_returns"]] * len(insert_data)
        insert_data["volatility_per_state"] = [emission_params["volatilities"]] * len(insert_data)

        # Add model metrics
        insert_data["aic"] = metrics["aic"]
        insert_data["bic"] = metrics["bic"]
        insert_data["log_likelihood"] = metrics["log_likelihood"]
        insert_data["n_states"] = n_states

        # Add GARCH conditional volatility if available (percentage-scaled)
        if garch_cond_vol is not None:
            cond_vol_values = garch_cond_vol.values
            if len(cond_vol_values) == len(insert_data):
                insert_data["garch_conditional_volatility"] = cond_vol_values
            else:
                logger.warning(f"GARCH cond_vol length {len(cond_vol_values)} != df length {len(insert_data)}, skipping")

        # Add macro features if present (US-only FRED columns: *_us and *_us_z)
        macro_cols = [col for col in df.columns if "_us" in col]
        for col in macro_cols:
            if col in df.columns:
                insert_data[col] = df[col]

        # Add enriched features if present (only columns that exist in mr_regime_states)
        _ENRICHED_TABLE_COLS = (
            ["log_return_z", "volatility_z", "rsi_z", "macd_z", "atr_z"]
            + [f"pc{i}" for i in range(1, 6)]
            + [f"pc{i}_{s}" for i in range(1, 6) for s in
               ["sma30", "sma50", "sma100", "sma200", "ema30", "ema50", "ema100", "ema200", "skew", "kurtosis"]]
        )
        for col in _ENRICHED_TABLE_COLS:
            if col in df.columns and col not in insert_data.columns:
                insert_data[col] = df[col]

        # Insert into ClickHouse
        client.insert_df(table, insert_data)
        logger.info(f"Logged {len(insert_data)} rows to ClickHouse table {table}")

        # Also log transition matrix with model metrics
        if model:
            log_transition_matrix(client, model, df["pair"].iloc[0], df["timeframe"].iloc[0], metrics,
                                  float(df["confidence_score"].mean()), config,
                                  n_features=df.get("_n_features", None),
                                  pca_metadata=df.attrs.get("pca_metadata"))

    except Exception as e:
        logger.error(f"Failed to log to ClickHouse: {e}", exc_info=True)


def log_transition_matrix(client, model, pair: str, timeframe: str, metrics: Dict,
                          avg_confidence: float, config: Dict,
                          n_features: int | None = None,
                          pca_metadata: Dict | None = None):
    """Log transition matrix and model quality metrics to ClickHouse."""
    try:
        transitions_table = config.get("clickhouse", {}).get("tables", {}).get("transitions", "mr_transition_matrices")

        transition_matrix = model.transmat_.tolist()

        # Serialize HMM params for warm-start on next run
        hmm_params_json = ""
        try:
            hmm_params_json = json.dumps({
                "startprob": model.startprob_.tolist(),
                "transmat": model.transmat_.tolist(),
                "means": model.means_.tolist(),
                "covars": model.covars_.tolist(),
                "n_features": n_features or (model.means_.shape[1] if model.means_.ndim > 1 else 0),
                "n_states": model.n_components,
            })
        except Exception as e:
            logger.warning(f"Failed to serialize HMM params: {e}")

        data = {
            "timestamp": [datetime.utcnow()],
            "pair": [pair],
            "timeframe": [timeframe],
            "n_states": [model.n_components],
            "transition_matrix": [transition_matrix],
            "aic": [float(metrics.get("aic", 0))],
            "bic": [float(metrics.get("bic", 0))],
            "log_likelihood": [float(metrics.get("log_likelihood", 0))],
            "avg_confidence": [float(avg_confidence)],
            "hmm_params": [hmm_params_json],
        }

        # Add PCA metadata if available
        if pca_metadata:
            data["pca_explained_variance"] = [pca_metadata.get("explained_variance_ratio", [])]
            data["pca_n_components"] = [pca_metadata.get("n_components", 0)]
        else:
            data["pca_explained_variance"] = [[]]
            data["pca_n_components"] = [0]

        df = pd.DataFrame(data)
        client.insert_df(transitions_table, df)
        logger.info(f"Logged transition matrix for {pair} {timeframe}")
    except Exception as e:
        logger.error(f"Failed to log transition matrix: {e}")


def train_and_predict(input_path: str, config: Dict) -> pd.DataFrame:
    """
    Main training and prediction pipeline.

    Args:
        input_path: Path to processed data CSV
        config: Configuration dictionary

    Returns:
        DataFrame with predictions
    """
    logger.info(f"Loading data from {input_path}")
    df = pd.read_csv(input_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Select features for HMM: prefer enriched (z-scored base + PCs + SMA/EMA + skew/kurtosis)
    base_raw = ["log_return", "volatility", "rsi", "macd", "atr"]
    base_z = [f"{c}_z" for c in base_raw]
    has_enriched = all(c in df.columns for c in base_z)
    if has_enriched:
        feature_cols = list(base_z)
        pc_cols = [c for c in df.columns if c.startswith("pc") and c in df.columns]
        feature_cols.extend([c for c in pc_cols if c in df.columns])
        logger.info(f"Using enriched features ({len(feature_cols)} cols)")
    else:
        feature_cols = [c for c in base_raw if c in df.columns]
        macro_cols = [col for col in df.columns if col.endswith("_us")]
        feature_cols.extend(macro_cols)
        logger.info(f"Using raw + macro features ({len(feature_cols)} cols)")

    feature_cols = [col for col in feature_cols if col in df.columns]
    features = df[feature_cols].fillna(0).values
    returns = df["log_return"].values

    # Load PCA metadata if available
    pca_metadata = None
    input_dir = Path(input_path).parent
    pca_metadata_path = input_dir / "pca_metadata.json"
    if pca_metadata_path.exists():
        try:
            with open(pca_metadata_path) as f:
                pca_metadata = json.load(f)
            logger.info(f"Loaded PCA metadata: {pca_metadata.get('n_components')} components, "
                        f"cumulative variance: {pca_metadata.get('cumulative_variance', 'N/A')}")
        except Exception as e:
            logger.warning(f"Failed to load PCA metadata: {e}")

    # Attempt warm-start from previous run's HMM parameters
    pair = df["pair"].iloc[0]
    timeframe = df["timeframe"].iloc[0]
    previous_params = _fetch_previous_hmm_params(config, pair, timeframe)

    # Train HMM
    model = train_hmm_model(features, config, previous_params=previous_params)

    # Predict regimes
    states, probabilities = predict_regimes(model, features)

    # Stabilize state labels: sort ascending by mean log_return so that
    # state 0 = bear (lowest return), state 1 = neutral, state 2 = bull (highest return).
    n_states = model.n_components
    mean_return_per_state = np.array([
        returns[states == s].mean() if (states == s).sum() > 0 else 0.0
        for s in range(n_states)
    ])
    sort_order = np.argsort(mean_return_per_state, kind='stable')  # ascending
    remap = np.empty(n_states, dtype=int)
    for new_label, old_label in enumerate(sort_order):
        remap[old_label] = new_label
    states = remap[states]
    probabilities = probabilities[:, sort_order]

    # Remap transition matrix to match new state ordering
    model.transmat_ = model.transmat_[sort_order][:, sort_order]

    # Add predictions to dataframe
    df["regime_state"] = states
    df["state_probabilities"] = list(probabilities)

    # Compute metrics
    metrics = compute_model_metrics(model, features)

    # Compute emission parameters using already-remapped states
    mean_returns = []
    volatilities = []
    for state in range(n_states):
        mask = states == state
        if mask.sum() > 0:
            mean_returns.append(float(returns[mask].mean()))
            volatilities.append(float(returns[mask].std()))
        else:
            mean_returns.append(0.0)
            volatilities.append(0.0)
    emission_params = {"mean_returns": mean_returns, "volatilities": volatilities}

    # Post-remap assertion: verify state ordering is correct
    if not all(mean_returns[i] <= mean_returns[i + 1] for i in range(len(mean_returns) - 1)):
        logger.warning(f"State ordering not strictly ascending after remap: {mean_returns}")

    # Compute confidence scores
    df["confidence_score"] = compute_confidence_score(probabilities, config)

    # Detect regime changes and durations
    df["regime_change"] = detect_regime_changes(states)
    df["regime_duration"] = compute_regime_duration(states)

    # Fit GARCH model and persist conditional volatility as a diagnostic
    _garch_result, garch_cond_vol = fit_garch_model(df["log_return"], config)

    # Attach metadata for log_transition_matrix
    df.attrs["pca_metadata"] = pca_metadata

    # Log warm-start delta if we had previous params
    if previous_params:
        try:
            prev_transmat = np.array(previous_params["transmat"])
            delta = np.abs(model.transmat_ - prev_transmat).mean()
            logger.info(f"Warm-start transition matrix delta: {delta:.6f}")
        except Exception:
            pass

    # Log to ClickHouse
    log_to_clickhouse(df, model, metrics, emission_params, config, garch_cond_vol=garch_cond_vol)

    logger.info(f"Training and prediction complete")
    logger.info(f"Metrics - AIC: {metrics['aic']:.2f}, BIC: {metrics['bic']:.2f}")
    logger.info(f"Emission params - Means: {emission_params['mean_returns']}")
    logger.info(f"Emission params - Volatilities: {emission_params['volatilities']}")

    return df


def main():
    """Main entry point for regime modeling."""
    input_path = os.environ.get("INPUT_PATH", "/workspace/processed_data.csv")
    output_path = os.environ.get("OUTPUT_PATH", "/workspace/regime_results.csv")

    logger.info(f"Starting regime modeling")

    try:
        config = load_config()
        df = train_and_predict(input_path, config)

        # Save results
        df.to_csv(output_path, index=False)
        logger.info(f"Saved results to {output_path}")

        return 0
    except Exception as e:
        logger.error(f"Regime modeling failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
