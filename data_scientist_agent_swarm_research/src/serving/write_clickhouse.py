"""Write features and predictions to ClickHouse."""
import pandas as pd
from src.shared.ch_client import get_client


def write_features(df: pd.DataFrame, pair: str, timeframe: str):
    """Write computed features to instrument_features table."""
    ch = get_client()

    non_feature = {"open", "high", "low", "close", "volume", "pair", "timeframe", "time", "complete"}
    feature_cols = [c for c in df.columns
                    if c not in non_feature and pd.api.types.is_numeric_dtype(df[c])]

    rows = []
    for ts, row in df.iterrows():
        features_map = {col: float(row[col]) for col in feature_cols if pd.notna(row[col])}
        rows.append({
            "pair": pair,
            "timeframe": timeframe,
            "timestamp": ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "features": features_map,
        })

    if rows:
        ch.insert(
            "fxs_instrument_features",
            data=[[r["pair"], r["timeframe"], r["timestamp"],
                   r["open"], r["high"], r["low"], r["close"], r["volume"],
                   r["features"]] for r in rows],
            column_names=["pair", "timeframe", "timestamp",
                         "open", "high", "low", "close", "volume", "features"],
        )


def write_predictions(df: pd.DataFrame, pair: str, timeframe: str):
    """Write predictions to predictions table."""
    ch = get_client()

    ch.insert(
        "fxs_predictions",
        data=[[pair, timeframe, row["timestamp"],
               row["model_registry"], row["model_version"],
               row["architecture"], row["pred_next_close"],
               None, None] for _, row in df.iterrows()],
        column_names=["pair", "timeframe", "timestamp",
                     "model_registry", "model_version",
                     "architecture", "pred_next_close",
                     "actual_close", "error_pips"],
    )
