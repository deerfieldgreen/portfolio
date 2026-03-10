#!/usr/bin/env python3
"""
Generate volume statistics from ClickHouse for trading session analysis.
Uses a single multi-pair query, non-overlapping session partitions (no double-counting),
and stored pair format. ClickHouse required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import warnings
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import clickhouse_connect
import numpy as np
import pandas as pd
import pmdarima as pm
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import mean_absolute_error, silhouette_score

# Optional: tslearn for TimeSeriesKMeans, optuna for broader IF tuning
_TSLEARN_AVAILABLE = False
_OPTUNA_AVAILABLE = False
try:
    from tslearn.clustering import TimeSeriesKMeans as _TSKMeans
    _TSLEARN_AVAILABLE = True
except ImportError:
    _TSKMeans = None  # type: ignore[misc, assignment]
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    _OPTUNA_AVAILABLE = True
except ImportError:
    optuna = None  # type: ignore[misc, assignment]


def _json_default(obj: Any) -> Any:
    """JSON serializer for datetime, numpy, pandas types."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _safe_float(x: Any) -> float:
    """Coerce to float; use 0.0 for NaN or missing."""
    if pd.isna(x):
        return 0.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ClickHouse config - standardized on CLICKHOUSE_DATABASE, CLICKHOUSE_USERNAME (no project-specific defaults)
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_SECURE = os.getenv("CLICKHOUSE_SECURE", "").lower() in ("1", "true", "yes")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "443" if CLICKHOUSE_SECURE else "8123"))
CLICKHOUSE_USERNAME = os.environ["CLICKHOUSE_USERNAME"]
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "oanda_data_statistics")

# Non-overlapping session partition (each hour 0–23 in exactly one bucket).
# Sydney 22–06, Tokyo 07–08, London 09–12, London–NY overlap 13–16, New York 17–21.
# NOTE: Must match data_processing/sessions.py (separate Docker image, cannot import).
SESSION_HOURS: Dict[str, List[int]] = {
    "sydney": [22, 23, 0, 1, 2, 3, 4, 5, 6],
    "tokyo": [7, 8],
    "london": [9, 10, 11, 12],
    "london_new_york_overlap": [13, 14, 15, 16],
    "new_york": [17, 18, 19, 20, 21],
}

DEFAULT_PAIRS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "AUD_USD",
    "USD_CAD", "NZD_USD", "EUR_JPY", "GBP_JPY", "AUD_JPY",
]


def _normalize_pair_formats(p: str) -> List[str]:
    """Candidate strings to match stored pair (e.g. EUR_USD, EURUSD, EUR/USD)."""
    return [
        p,
        p.replace("/", "_"),
        p.replace("/", ""),
        p.upper(),
        p.lower(),
    ]


def _parse_k_range(s: str) -> Tuple[int, int]:
    """Parse --k-range '2-8' -> (2, 8)."""
    a, b = s.strip().split("-")
    return (int(a.strip()), int(b.strip()))


def _parse_float_list(s: str) -> Tuple[float, ...]:
    """Parse --contamination-grid '0.05,0.1,0.15' -> (0.05, 0.1, 0.15)."""
    return tuple(float(x.strip()) for x in s.split(",") if x.strip())


def _arima_worker(
    args: Tuple[Any, ...],
) -> Optional[Tuple[str, float]]:
    """Module-level worker for parallel ARIMA fits. args = (pair, hour_gmt, dates, values, tune, fixed_order, seasonal_period, train_ratio, use_exog_dow, log_test_mae)."""
    (pair, hour_gmt, dates, values, tune, fixed_order, seasonal_period, train_ratio, use_exog_dow, log_test_mae) = args
    ser = pd.Series(values, index=pd.PeriodIndex(pd.to_datetime(dates), freq="D"))
    v = VolumeStatisticsGenerator._fit_arima_forecast(
        ser,
        tune=tune,
        fixed_order=fixed_order,
        seasonal_period=seasonal_period,
        train_ratio=train_ratio,
        use_exog_dow=use_exog_dow,
        log_test_mae=log_test_mae,
    )
    if v is not None:
        return (f"{pair}|{hour_gmt}", v)
    return None


@dataclass
class TuningConfig:
    """Configurable tuning ranges and options."""
    k_range: Tuple[int, int] = (2, 10)
    min_silhouette: float = 0.3
    use_tslearn_kmeans: bool = False
    contamination_grid: Tuple[float, ...] = (0.05, 0.075, 0.1, 0.125, 0.15)
    n_estimators_grid: Tuple[int, ...] = (50, 100, 150)
    use_optuna_if: bool = False
    if_lag_features: bool = True
    seasonal_period: int = 5
    train_ratio: float = 0.8
    arima_use_exog_dow: bool = True
    cache_path: Optional[Path] = None
    workers: int = field(default_factory=lambda: min(4, os.cpu_count() or 4))

    def cache_key(self, days_back: Optional[int], pairs: List[str]) -> str:
        """Stable key for cache lookup (config + days_back + pairs). None = all data."""
        raw = json.dumps({
            "days_back": days_back if days_back is not None else "all",
            "pairs": sorted(pairs),
            "k_range": list(self.k_range),
            "min_silhouette": self.min_silhouette,
            "contamination_grid": list(self.contamination_grid),
            "seasonal_period": self.seasonal_period,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def load_cache(self, days_back: Optional[int], pairs: List[str]) -> Optional[Dict[str, Any]]:
        """Load cached tuned params if path set and file exists with matching key."""
        if not self.cache_path:
            return None
        path = Path(self.cache_path)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("key") != self.cache_key(days_back, pairs):
                return None
            return data.get("params")
        except Exception:
            return None

    def save_cache(self, days_back: Optional[int], pairs: List[str], params: Dict[str, Any]) -> None:
        """Save tuned params to cache path."""
        if not self.cache_path:
            return
        path = Path(self.cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w") as f:
                json.dump({"key": self.cache_key(days_back, pairs), "params": params}, f)
            logger.info("  Cache saved: %s", path)
        except Exception as e:
            logger.debug("Cache save failed: %s", e)


class VolumeStatisticsGenerator:
    """Generate volume statistics from ClickHouse. Single multi-pair query, no double-counting."""

    def __init__(self) -> None:
        self._client: Any = None
        self._table: str = ""
        self._pair_col: str = ""
        self._volume_col: str = ""
        self._ts_col: str = ""
        self._timeframe: Optional[str] = None  # e.g. H1, H4; filters ohlcv_data when set

    def set_timeframe(self, tf: str) -> None:
        """Restrict queries to this OHLCV timeframe (e.g. H1, H4). Table must have 'timeframe' column."""
        self._timeframe = tf.strip().upper() if tf else None

    def _where_clause(self, days_back: Optional[int]) -> str:
        """Build WHERE clause for time and optional timeframe. Returns 'WHERE ...' or ''."""
        parts: List[str] = []
        if days_back is not None:
            parts.append(f"{self._ts_col} >= now() - INTERVAL {days_back} DAY")
        if self._timeframe:
            parts.append(f"timeframe = '{self._timeframe}'")
        if not parts:
            return ""
        return "WHERE " + " AND ".join(parts)

    def connect_clickhouse(self) -> None:
        try:
            self._client = clickhouse_connect.get_client(
                host=CLICKHOUSE_HOST,
                port=CLICKHOUSE_PORT,
                username=CLICKHOUSE_USERNAME,
                password=CLICKHOUSE_PASSWORD,
                database=CLICKHOUSE_DATABASE,
                secure=CLICKHOUSE_SECURE,
            )
            v = self._client.command("SELECT version()")
            logger.info("✅ Connected to ClickHouse: %s", v)
        except Exception as e:
            raise RuntimeError(f"ClickHouse is required but connection failed: {e}") from e

    def _discover_schema(self) -> bool:
        """Resolve raw table and columns. We use raw for time-bounded queries; market_sessions_volume_by_hour MV has no date."""
        q = f"SHOW TABLES FROM {CLICKHOUSE_DATABASE}"
        tables = [r[0] for r in self._client.query(q).result_rows]
        raw = None
        for t in tables:
            if "market_data" in t.lower() or "ohlcv" in t.lower() or "raw" in t.lower():
                raw = t
                break
        if not raw:
            logger.warning("No suitable raw table found. Available: %s", tables)
            return False

        desc = self._client.query(f"DESCRIBE TABLE {CLICKHOUSE_DATABASE}.{raw}")
        cols = [r[0] for r in desc.result_rows]
        pair_col = next((c for c in ["pair", "symbol", "instrument", "currency_pair"] if c in cols), None)
        vol_col = next((c for c in ["volume", "vol", "trading_volume"] if c in cols), None)
        ts_col = next((c for c in ["timestamp", "time", "datetime", "date_time", "time_stamp", "bar_time"] if c in cols), None)
        if not pair_col or not vol_col or not ts_col:
            logger.warning("Missing pair/volume/timestamp columns. Found: %s", cols)
            return False

        self._table = f"{CLICKHOUSE_DATABASE}.{raw}"
        self._pair_col = pair_col
        self._volume_col = vol_col
        self._ts_col = ts_col
        # Optional OHLC for volatility/ATR correlation
        self._open_col = next((c for c in ["open", "o"] if c in cols), None)
        self._high_col = next((c for c in ["high", "h"] if c in cols), None)
        self._low_col = next((c for c in ["low", "l"] if c in cols), None)
        self._close_col = next((c for c in ["close", "c"] if c in cols), None)
        self._has_ohlc = all([self._open_col, self._high_col, self._low_col, self._close_col])
        if self._has_ohlc:
            logger.info("OHLC columns found: open=%s, high=%s, low=%s, close=%s", self._open_col, self._high_col, self._low_col, self._close_col)
        logger.info("Using table=%s, pair=%s, volume=%s, timestamp=%s", self._table, pair_col, vol_col, ts_col)
        return True

    def _run_diagnostics(self, days_back: Optional[int]) -> Tuple[List[str], pd.DataFrame]:
        """Log DISTINCT pairs, pair counts, and return stored pairs + per-pair counts. days_back=None = all data."""
        where = self._where_clause(days_back)
        # Distinct pairs (same time/timeframe window)
        q1 = f"SELECT DISTINCT {self._pair_col} FROM {self._table} {where} ORDER BY {self._pair_col}"
        logger.info("Diagnostics – distinct pairs query: %s", q1)
        distinct = self._client.query(q1)
        stored_pairs = [r[0] for r in distinct.result_rows]
        logger.info("Stored pairs (%d): %s", len(stored_pairs), stored_pairs[:20] if len(stored_pairs) > 20 else stored_pairs)

        # Per-pair row counts
        q2 = f"""
        SELECT {self._pair_col} AS pair, count() AS cnt
        FROM {self._table}
        {where}
        GROUP BY pair
        ORDER BY pair
        """
        logger.info("Diagnostics – pair counts query: %s", q2.strip())
        pc = self._client.query_df(q2)
        logger.info("Pair counts (%s):\n%s", f"last {days_back} days" if days_back is not None else "all data", pc.to_string() if not pc.empty else "(empty)")
        return stored_pairs, pc

    def _query_all_pairs_hourly(self, days_back: Optional[int]) -> pd.DataFrame:
        """Single query: all pairs, hourly aggregates. days_back=None = all data (no time limit)."""
        where = self._where_clause(days_back)
        query = f"""
        SELECT
            {self._pair_col} AS pair,
            toHour({self._ts_col}) AS hour_gmt,
            sum({self._volume_col}) AS total_volume,
            count() AS bar_count,
            min({self._ts_col}) AS first_ts,
            max({self._ts_col}) AS last_ts
        FROM {self._table}
        {where}
        GROUP BY pair, hour_gmt
        ORDER BY pair, hour_gmt
        """
        logger.info("Executing multi-pair hourly query (%s):\n%s", "all data" if days_back is None else f"last {days_back} days", query.strip())
        df = self._client.query_df(query)
        return df

    def _query_all_pairs_hourly_bars(self, days_back: Optional[int]) -> pd.DataFrame:
        """Per-bar rows per hour for percentile/z-score in hourly breakdown. days_back=None = all data."""
        where = self._where_clause(days_back)
        query = f"""
        SELECT
            {self._pair_col} AS pair,
            toHour({self._ts_col}) AS hour_gmt,
            toDate({self._ts_col}) AS date,
            {self._volume_col} AS bar_volume,
            {self._ts_col} AS ts
        FROM {self._table}
        {where}
        ORDER BY pair, hour_gmt, ts
        """
        logger.info("Executing multi-pair hourly bars (disaggregated) query (%s)", "all data" if days_back is None else f"last {days_back} days")
        return self._client.query_df(query)

    @staticmethod
    def _enhanced_hourly_breakdown(hourly_bars_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Compute hourly breakdown with p75 volume and z-scores from per-bar volumes. Groups by (pair, hour_gmt)."""
        if hourly_bars_df.empty or "bar_volume" not in hourly_bars_df.columns or "ts" not in hourly_bars_df.columns:
            return []
        required = {"pair", "hour_gmt", "bar_volume", "ts"}
        if not required.issubset(hourly_bars_df.columns):
            return []
        enhanced: List[Dict[str, Any]] = []
        for (pair, hour_gmt), group in hourly_bars_df.groupby(["pair", "hour_gmt"]):
            volumes = group["bar_volume"].values.astype(float)
            if len(volumes) == 0:
                continue
            avg_vol = float(np.mean(volumes))
            std_vol = float(np.std(volumes)) if len(volumes) > 1 else 0.0
            z_scores = (volumes - avg_vol) / std_vol if std_vol > 0 else np.zeros_like(volumes)
            first_ts = group["ts"].min()
            last_ts = group["ts"].max()
            entry: Dict[str, Any] = {
                "pair": pair,
                "hour_gmt": int(hour_gmt),
                "total_volume": float(np.sum(volumes)),
                "bar_count": len(volumes),
                "first_ts": first_ts.isoformat() if hasattr(first_ts, "isoformat") else first_ts,
                "last_ts": last_ts.isoformat() if hasattr(last_ts, "isoformat") else last_ts,
                "p75_volume": float(np.percentile(volumes, 75)),
                "avg_z_score": float(np.mean(z_scores)),
                "max_z_score": float(np.max(z_scores)),
            }
            enhanced.append(entry)
        return enhanced

    def _coverage_query(self, days_back: Optional[int]) -> pd.DataFrame:
        """Per-pair coverage: distinct days, first_ts, last_ts. days_back=None = all data."""
        where = self._where_clause(days_back)
        q = f"""
        SELECT
            {self._pair_col} AS pair,
            countDistinct(toDate({self._ts_col})) AS distinct_days,
            min({self._ts_col}) AS first_ts,
            max({self._ts_col}) AS last_ts
        FROM {self._table}
        {where}
        GROUP BY pair
        """
        return self._client.query_df(q)

    def _query_daily_totals(self, days_back: Optional[int]) -> pd.DataFrame:
        """Per-pair per-day total volume for anomaly detection. days_back=None = all data."""
        where = self._where_clause(days_back)
        q = f"""
        SELECT
            {self._pair_col} AS pair,
            toDate({self._ts_col}) AS date,
            sum({self._volume_col}) AS daily_volume
        FROM {self._table}
        {where}
        GROUP BY pair, date
        ORDER BY pair, date
        """
        return self._client.query_df(q)

    def _query_hourly_totals(self, days_back: Optional[int]) -> pd.DataFrame:
        """Per-pair per-date per-hour total volume for per-hour anomaly detection. days_back=None = all data."""
        where = self._where_clause(days_back)
        q = f"""
        SELECT
            {self._pair_col} AS pair,
            toDate({self._ts_col}) AS date,
            toHour({self._ts_col}) AS hour_gmt,
            sum({self._volume_col}) AS hourly_volume
        FROM {self._table}
        {where}
        GROUP BY pair, date, hour_gmt
        ORDER BY pair, date, hour_gmt
        """
        return self._client.query_df(q)

    def _query_hourly_timeseries(self, days_back: Optional[int]) -> pd.DataFrame:
        """Per-pair per-date per-hour volume for ARIMA time-series. days_back=None = all data."""
        where = self._where_clause(days_back)
        q = f"""
        SELECT
            {self._pair_col} AS pair,
            toDate({self._ts_col}) AS date,
            toHour({self._ts_col}) AS hour_gmt,
            sum({self._volume_col}) AS total_volume
        FROM {self._table}
        {where}
        GROUP BY pair, date, hour_gmt
        ORDER BY pair, date, hour_gmt
        """
        return self._client.query_df(q)

    def _query_ohlcv(self, days_back: Optional[int]) -> pd.DataFrame:
        """OHLCV rows for ATR/volume correlation. Requires open, high, low, close columns. days_back=None = all data."""
        if not getattr(self, "_has_ohlc", False):
            return pd.DataFrame()
        where = self._where_clause(days_back)
        q = f"""
        SELECT
            {self._pair_col} AS pair,
            {self._ts_col} AS ts,
            {self._open_col} AS open,
            {self._high_col} AS high,
            {self._low_col} AS low,
            {self._close_col} AS close,
            {self._volume_col} AS volume
        FROM {self._table}
        {where}
        ORDER BY pair, ts
        """
        return self._client.query_df(q)

    @staticmethod
    def _compute_volatility_correlations(ohlcv_df: pd.DataFrame, atr_period: int = 14) -> Dict[str, float]:
        """Per-pair correlation of ATR with volume. Returns {pair: correlation}."""
        if ohlcv_df.empty or "pair" not in ohlcv_df.columns:
            return {}
        required = {"pair", "ts", "high", "low", "close", "volume"}
        if not required.issubset(ohlcv_df.columns):
            return {}
        correlations: Dict[str, float] = {}
        for pair, group in ohlcv_df.groupby("pair"):
            group = group.sort_values("ts")
            prev_close = group["close"].shift(1)
            tr = np.maximum(
                group["high"].values - group["low"].values,
                np.maximum(
                    np.abs(group["high"].values - prev_close.values),
                    np.abs(group["low"].values - prev_close.values),
                ),
            )
            atr_series = pd.Series(tr, index=group.index).rolling(window=atr_period).mean().dropna()
            vol_aligned = group.loc[atr_series.index, "volume"].astype(float)
            atr_vals = atr_series.values
            vol = vol_aligned.values
            if len(atr_vals) > 1 and len(vol) > 1 and len(atr_vals) == len(vol):
                corr = float(np.corrcoef(atr_vals, vol)[0, 1])
                correlations[pair] = corr if not np.isnan(corr) else 0.0
            else:
                correlations[pair] = 0.0
        return correlations

    @staticmethod
    def _session_stats_from_hourly(hourly: pd.DataFrame) -> Dict[str, Any]:
        """Compute per-session stats from hourly df. Non-overlapping partition – each hour counted once."""
        hourly = hourly.copy()
        hourly["hour_gmt"] = hourly["hour_gmt"].astype(int)
        session_stats: Dict[str, Any] = {}
        for name, hours in SESSION_HOURS.items():
            mask = hourly["hour_gmt"].isin(hours)
            sub = hourly.loc[mask]
            vol = float(sub["total_volume"].sum())
            cnt = int(sub["bar_count"].sum())
            avg_volume = vol / cnt if cnt > 0 else 0.0
            std_volume = float(sub["total_volume"].std()) if len(sub) > 1 else 0.0
            if pd.isna(std_volume):
                std_volume = 0.0
            session_stats[name] = {
                "hours": hours,
                "volume": vol,
                "count": cnt,
                "avg_volume": avg_volume,
                "std_volume": std_volume,
                "median_volume": _safe_float(sub["total_volume"].median()),
                "min_volume": _safe_float(sub["total_volume"].min()),
                "max_volume": _safe_float(sub["total_volume"].max()),
                "cv": (std_volume / avg_volume) if avg_volume else 0.0,
            }
        return session_stats

    @staticmethod
    def _select_n_clusters(
        norm: pd.DataFrame,
        k_min: int = 2,
        k_max: int = 10,
        min_silhouette: float = 0.3,
    ) -> Tuple[int, float]:
        """Select n_clusters by maximizing silhouette over [k_min, k_max]. If best_score < min_silhouette, use k=1 and log warning."""
        n = len(norm)
        if n < 2:
            return 1, 0.0
        k_max = min(k_max, n - 1)
        if k_min >= k_max:
            return max(1, k_min), 0.0
        best_k, best_score = k_min, -1.0
        logger.info("  KMeans: searching n_clusters in [%d, %d] by silhouette (n_pairs=%d, min_silhouette=%.2f)", k_min, k_max, n, min_silhouette)
        for k in range(k_min, k_max + 1):
            km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(norm)
            score = silhouette_score(norm, km.labels_)
            if score > best_score:
                best_score = score
                best_k = k
        if best_score < min_silhouette:
            logger.warning(
                "  KMeans: best silhouette=%.4f below threshold %.2f; defaulting to n_clusters=1 (no meaningful clustering)",
                best_score,
                min_silhouette,
            )
            best_k, best_score = 1, best_score
        else:
            logger.info("  KMeans: selected n_clusters=%d (silhouette=%.4f)", best_k, best_score)
        return best_k, best_score

    @staticmethod
    def _compute_pair_clusters(
        hourly_df: pd.DataFrame,
        n_clusters: Optional[int] = None,
        tune_k: bool = True,
        k_range: Tuple[int, int] = (2, 10),
        min_silhouette: float = 0.3,
        use_tslearn: bool = False,
    ) -> Dict[str, int]:
        """Cluster pairs by intraday volume pattern. If tune_k, n_clusters chosen by silhouette; if best < min_silhouette, k=1.
        If use_tslearn and tslearn available, use TimeSeriesKMeans (DTW) for shape matching."""
        if hourly_df.empty or "pair" not in hourly_df.columns or "hour_gmt" not in hourly_df.columns:
            return {}
        piv = hourly_df.pivot(index="pair", columns="hour_gmt", values="total_volume").fillna(0)
        if piv.empty or piv.sum(axis=1).eq(0).all():
            return {}
        norm = piv.div(piv.sum(axis=1), axis=0)
        n = len(norm)
        if tune_k:
            n_clusters, _ = VolumeStatisticsGenerator._select_n_clusters(
                norm, k_min=k_range[0], k_max=k_range[1], min_silhouette=min_silhouette
            )
        if n_clusters is None:
            n_clusters = 3
        k = min(n_clusters, n)
        if k == 1:
            labels = dict(zip(norm.index.tolist(), [0] * n))
            logger.info("  KMeans: assigned %d pairs to 1 cluster", n)
            return labels
        if use_tslearn and _TSLEARN_AVAILABLE and _TSKMeans is not None:
            # TimeSeriesKMeans expects (n_ts, sz, d): (n_samples, n_timesteps, n_features)
            X_ts = norm.values.reshape(n, -1, 1)
            km = _TSKMeans(n_clusters=k, random_state=42, n_init=10, metric="dtw").fit(X_ts)
            labels = dict(zip(norm.index.tolist(), km.labels_.tolist()))
            logger.info("  KMeans: TimeSeriesKMeans (DTW) assigned %d pairs to %d clusters", n, k)
            return labels
        km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(norm)
        labels = dict(zip(norm.index.tolist(), km.labels_.tolist()))
        logger.info("  KMeans: assigned %d pairs to %d clusters", len(labels), k)
        return labels

    IF_STABILITY_RUNS = 3

    @staticmethod
    def _build_if_features(vol: np.ndarray, use_lags: bool, n_lags: int = 2) -> Tuple[np.ndarray, np.ndarray]:
        """Build feature matrix: vol only or [vol, vol_lag1, vol_lag2]. Returns (X, mask) where mask indexes rows with valid lags (len = n - n_lags)."""
        vol = np.asarray(vol, dtype=float).ravel()
        if not use_lags or len(vol) <= n_lags:
            return vol.reshape(-1, 1), np.arange(len(vol))
        # X[i] = [vol[i+n_lags], vol[i+n_lags-1], ..., vol[i+1]] so row i corresponds to date index i + n_lags
        X = np.column_stack([vol[n_lags - j : len(vol) - j] for j in range(n_lags + 1)])
        indices = np.arange(n_lags, len(vol))
        return X, indices

    @staticmethod
    def _tune_isolation_forest(
        X: np.ndarray,
        contamination_grid: Sequence[float],
        n_estimators_grid: Sequence[int],
        use_optuna: bool = False,
        stability_runs: int = 3,
    ) -> Tuple[float, int]:
        """Select (contamination, n_estimators): stability criterion or Optuna if use_optuna and available."""
        if use_optuna and _OPTUNA_AVAILABLE and optuna is not None:
            def objective(trial: Any) -> float:
                c = trial.suggest_float("contamination", min(contamination_grid), max(contamination_grid))
                n = trial.suggest_int("n_estimators", min(n_estimators_grid), max(n_estimators_grid))
                counts = []
                for seed in range(stability_runs):
                    iso = IsolationForest(random_state=42 + seed, contamination=c, n_estimators=n).fit(X)
                    counts.append(int((iso.predict(X) == -1).sum()))
                return float(np.std(counts))
            study = optuna.create_study(direction="minimize")
            study.optimize(objective, n_trials=min(30, len(contamination_grid) * len(n_estimators_grid) * 2), show_progress_bar=False)
            best = study.best_params
            return (float(best["contamination"]), int(best["n_estimators"]))
        best_std, best_c, best_n = float("inf"), 0.1, 100
        for c in contamination_grid:
            for n in n_estimators_grid:
                counts: List[int] = []
                for seed in range(stability_runs):
                    iso = IsolationForest(random_state=42 + seed, contamination=c, n_estimators=n).fit(X)
                    pred = iso.predict(X)
                    counts.append(int((pred == -1).sum()))
                std = float(np.std(counts))
                if std < best_std:
                    best_std, best_c, best_n = std, c, n
        return best_c, best_n

    @staticmethod
    def _compute_volume_anomalies(
        daily_df: pd.DataFrame,
        tune: bool = True,
        tuning_config: Optional[TuningConfig] = None,
        cache_if: Optional[Dict[str, Dict[str, Any]]] = None,
        out_if_params: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Flag unusual volume days per pair using IsolationForest. With if_lag_features, uses [vol, vol_lag1, vol_lag2].
        If tune, selects contamination/n_estimators by stability (or Optuna when use_optuna_if).
        If out_if_params is provided, fills it with {pair: {contamination, n_estimators}} for caching."""
        if daily_df.empty or "pair" not in daily_df.columns or "daily_volume" not in daily_df.columns:
            return {}
        cfg = tuning_config or TuningConfig()
        contamination_grid = cfg.contamination_grid
        n_estimators_grid = cfg.n_estimators_grid
        use_lags = cfg.if_lag_features
        use_optuna = cfg.use_optuna_if and _OPTUNA_AVAILABLE
        pairs_for_if = [p for p, g in daily_df.groupby("pair") if len(g) >= 3]
        if tune and pairs_for_if:
            logger.info(
                "  Isolation Forest: tuning for %d pairs (lags=%s, optuna=%s)",
                len(pairs_for_if),
                use_lags,
                use_optuna,
            )
        out: Dict[str, Any] = {}
        if out_if_params is not None:
            out_if_params.clear()
        for pair, grp in daily_df.groupby("pair"):
            vol = grp["daily_volume"].values.astype(float)
            if len(vol) < 3:
                continue
            dates = grp["date"].tolist()
            cached = (cache_if or {}).get(pair)
            if tune and cached is not None:
                contamination, n_estimators = cached.get("contamination", 0.1), cached.get("n_estimators", 100)
            elif tune:
                X, indices = VolumeStatisticsGenerator._build_if_features(vol, use_lags)
                contamination, n_estimators = VolumeStatisticsGenerator._tune_isolation_forest(
                    X, contamination_grid, n_estimators_grid, use_optuna=use_optuna, stability_runs=VolumeStatisticsGenerator.IF_STABILITY_RUNS
                )
            else:
                contamination, n_estimators = 0.1, 100
            if out_if_params is not None:
                out_if_params[pair] = {"contamination": contamination, "n_estimators": n_estimators}
            X_fit, indices = VolumeStatisticsGenerator._build_if_features(vol, use_lags)
            iso = IsolationForest(random_state=42, contamination=contamination, n_estimators=n_estimators).fit(X_fit)
            pred = iso.predict(X_fit)
            pred_full = np.ones(len(vol), dtype=int)
            pred_full[indices] = pred
            if tune:
                logger.info("    %s: contamination=%.3f, n_estimators=%d → %d anomaly days", pair, contamination, n_estimators, int((pred_full == -1).sum()))
            out[pair] = [
                {
                    "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "daily_volume": float(v),
                    "is_anomaly": bool(pred_full[i] == -1),
                }
                for i, (d, v) in enumerate(zip(dates, vol))
            ]
        if out and not tune:
            logger.info("  Isolation Forest: fitted %d pairs (fixed contamination=0.1, n_estimators=100)", len(out))
        return out

    @staticmethod
    def _compute_hourly_volume_anomalies(
        hourly_df: pd.DataFrame,
        tune: bool = True,
        tuning_config: Optional[TuningConfig] = None,
        cache_if: Optional[Dict[str, Dict[str, Any]]] = None,
        out_if_params: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Flag unusual volume at (pair, date, hour_gmt) using Isolation Forest. Features: hourly_volume, lag1, dow."""
        if hourly_df.empty or "pair" not in hourly_df.columns or "hourly_volume" not in hourly_df.columns:
            return {}
        if "date" not in hourly_df.columns or "hour_gmt" not in hourly_df.columns:
            return {}
        cfg = tuning_config or TuningConfig()
        contamination_grid = cfg.contamination_grid
        n_estimators_grid = cfg.n_estimators_grid
        use_optuna = cfg.use_optuna_if and _OPTUNA_AVAILABLE
        pairs_for_if = [p for p, g in hourly_df.groupby("pair") if len(g) >= 3]
        if tune and pairs_for_if:
            logger.info(
                "  Isolation Forest (hourly): tuning for %d pairs (optuna=%s)",
                len(pairs_for_if),
                use_optuna,
            )
        out: Dict[str, List[Dict[str, Any]]] = {}
        if out_if_params is not None:
            out_if_params.clear()
        for pair, pair_df in hourly_df.groupby("pair"):
            pair_df = pair_df.sort_values(["date", "hour_gmt"]).copy()
            pair_df["lag1"] = pair_df["hourly_volume"].shift(1)
            pair_df["dow"] = pd.to_datetime(pair_df["date"]).dt.dayofweek
            features_df = pair_df[["hourly_volume", "lag1", "dow"]].dropna()
            if len(features_df) < 3:
                continue
            X = features_df.values.astype(float)
            cached = (cache_if or {}).get(pair)
            if tune and cached is not None:
                contamination = cached.get("contamination", 0.1)
                n_estimators = cached.get("n_estimators", 100)
            elif tune:
                contamination, n_estimators = VolumeStatisticsGenerator._tune_isolation_forest(
                    X,
                    contamination_grid,
                    n_estimators_grid,
                    use_optuna=use_optuna,
                    stability_runs=VolumeStatisticsGenerator.IF_STABILITY_RUNS,
                )
            else:
                contamination, n_estimators = 0.1, 100
            if out_if_params is not None:
                out_if_params[pair] = {"contamination": contamination, "n_estimators": n_estimators}
            model = IsolationForest(contamination=contamination, n_estimators=n_estimators, random_state=42).fit(X)
            pred = model.predict(X)
            scores = model.score_samples(X)
            aligned = pair_df.loc[features_df.index]
            records: List[Dict[str, Any]] = []
            for i, idx in enumerate(features_df.index):
                row = aligned.loc[idx]
                records.append({
                    "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]),
                    "hour_gmt": int(row["hour_gmt"]),
                    "hourly_volume": float(row["hourly_volume"]),
                    "is_anomaly": bool(pred[i] == -1),
                    "anomaly_score": float(scores[i]),
                })
            out[pair] = records
            if tune and records:
                n_anom = sum(1 for r in records if r["is_anomaly"])
                logger.info("    %s (hourly): contamination=%.3f, n_estimators=%d → %d anomaly date-hours", pair, contamination, n_estimators, n_anom)
        if out and not tune:
            logger.info("  Isolation Forest (hourly): fitted %d pairs (fixed contamination=0.1, n_estimators=100)", len(out))
        return out

    @staticmethod
    def _fit_arima_forecast(
        ser: pd.Series,
        tune: bool = True,
        fixed_order: Tuple[int, int, int] = (1, 0, 0),
        seasonal_period: int = 5,
        train_ratio: float = 0.8,
        use_exog_dow: bool = True,
        log_test_mae: bool = False,
    ) -> Optional[float]:
        """Fit ARIMA (optionally SARIMAX with day-of-week exog). 80/20 hold-out: tune on train, evaluate MAE on test; then refit on full for one-step forecast."""
        ser = ser.astype(float).copy()
        if not isinstance(ser.index, pd.PeriodIndex) or getattr(ser.index, "freq", None) is None:
            ser.index = pd.PeriodIndex(pd.to_datetime(ser.index), freq="D")
        n = len(ser)
        if n < max(seasonal_period * 2, 8):
            train_ratio = 1.0
        # Exogenous: day-of-week (0=Mon .. 6=Sun); use only if we have enough variety
        exog = None
        if use_exog_dow and n >= 5:
            dow = np.array([ser.index[i].dayofweek for i in range(n)])
            exog = pd.DataFrame({"dow": dow}, index=ser.index)
        train_size = int(n * train_ratio) if train_ratio < 1.0 else n
        train_ser = ser.iloc[:train_size]
        train_exog = exog.iloc[:train_size] if exog is not None else None
        test_ser = ser.iloc[train_size:] if train_size < n else None
        test_exog = exog.iloc[train_size:] if exog is not None and train_size < n else None

        def _fit_and_forecast(y: pd.Series, X: Optional[pd.DataFrame], steps: int, X_future: Optional[pd.DataFrame] = None) -> Optional[Tuple[Any, np.ndarray]]:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*[Cc]onvergence.*")
                warnings.filterwarnings("ignore", module="statsmodels")
                try:
                    if tune and len(y) >= max(seasonal_period * 2, 8):
                        model = pm.arima.auto_arima(
                            y,
                            X=X,
                            seasonal=True,
                            m=seasonal_period,
                            stepwise=True,
                            trace=False,
                            maxiter=50,
                            suppress_warnings=True,
                            error_action="ignore",
                        )
                    else:
                        model = pm.arima.ARIMA(order=fixed_order)
                        model.fit(y, X=X)
                    if steps <= 0:
                        return (model, np.array([]))
                    fcast = model.predict(n_periods=steps, X=X_future)
                    return (model, np.asarray(fcast))
                except Exception:
                    return None

        if train_ratio < 1.0 and test_ser is not None and len(test_ser) > 0:
            res = _fit_and_forecast(train_ser, train_exog, len(test_ser), test_exog)
            if res is not None:
                _, test_fcast = res
                mae = mean_absolute_error(test_ser.values, test_fcast)
                if log_test_mae:
                    logger.debug("  ARIMA hold-out MAE=%.2f (test n=%d)", mae, len(test_ser))
        res = _fit_and_forecast(ser, exog, 1, VolumeStatisticsGenerator._exog_next(ser, exog))
        if res is None:
            return None
        model, fcast = res
        if len(fcast) == 0:
            return None
        return float(fcast[0])

    @staticmethod
    def _exog_next(ser: pd.Series, exog: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """One-row exog for next period (day-of-week)."""
        if exog is None:
            return None
        next_period = ser.index[-1] + 1
        next_dow = next_period.dayofweek
        return pd.DataFrame({"dow": [next_dow]}, index=[next_period])

    @staticmethod
    def _compute_hourly_forecasts(
        hourly_ts_df: pd.DataFrame,
        tune: bool = True,
        fixed_order: Tuple[int, int, int] = (1, 0, 0),
        min_points: int = 5,
        seasonal_period: int = 5,
        train_ratio: float = 0.8,
        use_exog_dow: bool = True,
        log_test_mae: bool = False,
        workers: int = 1,
    ) -> Dict[str, Any]:
        """Per (pair, hour_gmt) fit ARIMA (optionally with day-of-week exog). 80/20 hold-out validates MAE. If workers>1, parallelize."""
        if hourly_ts_df.empty or "date" not in hourly_ts_df.columns or "hour_gmt" not in hourly_ts_df.columns:
            return {}
        groups = [(p, h) for (p, h), g in hourly_ts_df.groupby(["pair", "hour_gmt"]) if len(g) >= min_points]
        logger.info(
            "  ARIMA: fitting %d (pair, hour) series (tune=%s, seasonal m=%d, exog_dow=%s, train_ratio=%.2f)",
            len(groups),
            tune,
            seasonal_period,
            use_exog_dow,
            train_ratio,
        )
        forecasts: Dict[str, Any] = {}
        skipped = 0
        if workers > 1:
            args_list = []
            for (pair, hour_gmt), grp in hourly_ts_df.groupby(["pair", "hour_gmt"]):
                grp_sorted = grp.sort_values("date")
                ser = grp_sorted.set_index("date")["total_volume"]
                if len(ser) < min_points:
                    skipped += 1
                    continue
                dates = [ser.index[i].strftime("%Y-%m-%d") for i in range(len(ser))]
                args_list.append((pair, int(hour_gmt), dates, ser.values.tolist(), tune, fixed_order, seasonal_period, train_ratio, use_exog_dow, log_test_mae))
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_arima_worker, a): a for a in args_list}
                for fut in as_completed(futures):
                    try:
                        result = fut.result()
                        if result is not None:
                            key, fcast_val = result
                            pair, hour_gmt = key.split("|")[0], int(key.split("|")[1])
                            forecasts[key] = {"pair": pair, "hour_gmt": hour_gmt, "next_volume_forecast": fcast_val}
                            if len(forecasts) % 50 == 0:
                                logger.info("    ARIMA: %d/%d series fitted", len(forecasts), len(args_list))
                        else:
                            skipped += 1
                    except Exception as e:
                        logger.debug("ARIMA worker failed: %s", e)
                        skipped += 1
        else:
            for (pair, hour_gmt), grp in hourly_ts_df.groupby(["pair", "hour_gmt"]):
                grp_sorted = grp.sort_values("date")
                ser = grp_sorted.set_index("date")["total_volume"]
                if len(ser) < min_points:
                    skipped += 1
                    continue
                fcast_val = VolumeStatisticsGenerator._fit_arima_forecast(
                    ser,
                    tune=tune,
                    fixed_order=fixed_order,
                    seasonal_period=seasonal_period,
                    train_ratio=train_ratio,
                    use_exog_dow=use_exog_dow,
                    log_test_mae=log_test_mae,
                )
                if fcast_val is not None:
                    key = f"{pair}|{int(hour_gmt)}"
                    forecasts[key] = {"pair": pair, "hour_gmt": int(hour_gmt), "next_volume_forecast": fcast_val}
                    if (len(forecasts) % 50) == 0:
                        logger.info("    ARIMA: %d/%d series fitted", len(forecasts), len(groups))
                else:
                    skipped += 1
                    logger.debug("ARIMA skip %s hour %s (fit failed)", pair, hour_gmt)
        logger.info("  ARIMA: fitted %d series, skipped %d (too short or fit failed)", len(forecasts), skipped)
        return forecasts

    def generate_session_statistics(
        self,
        pairs: List[str],
        days_back: Optional[int] = None,
        tune_hyperparams: bool = True,
        tuning_config: Optional[TuningConfig] = None,
    ) -> Dict[str, Any]:
        """Generate volume statistics. Uses single multi-pair query and stored pair format.
        days_back=None (default) = consume all data from ClickHouse (no time limit).
        If tune_hyperparams is True, KMeans k, Isolation Forest (contamination, n_estimators), and ARIMA order are tuned.
        tuning_config controls ranges (k_range, contamination_grid, seasonal_period, etc.) and cache/workers."""
        self.connect_clickhouse()
        if not self._discover_schema():
            raise RuntimeError("Schema discovery failed.")

        stored_pairs, pair_counts_df = self._run_diagnostics(days_back)
        statistics: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "days_analyzed": days_back if days_back is not None else "all",
            "pairs": {},
            "summary": {},
        }

        hourly_df = self._query_all_pairs_hourly(days_back)
        hourly_bars_df = self._query_all_pairs_hourly_bars(days_back)
        if hourly_df.empty:
            logger.warning("No hourly data returned. Check table and time range.")
            for p in pairs:
                statistics["pairs"][p] = {"pair": p, "market_sessions_data": None}
            statistics["summary"] = self._generate_summary(statistics["pairs"])
            return statistics

        coverage_df = self._coverage_query(days_back)

        # Map requested pair -> stored pair (use only stored format)
        def resolve(p: str) -> Optional[str]:
            for fmt in _normalize_pair_formats(p):
                if fmt in stored_pairs:
                    return fmt
            return None

        for requested in pairs:
            stored = resolve(requested)
            pair_stats: Dict[str, Any] = {"pair": requested, "market_sessions_data": None}
            if stored is None:
                logger.info("Pair %s not found in DB (stored: %s); skipping.", requested, stored_pairs[:5])
                statistics["pairs"][requested] = pair_stats
                continue

            sub = hourly_df[hourly_df["pair"] == stored]
            if sub.empty:
                logger.info("No hourly rows for %s (stored as %s); skipping.", requested, stored)
                statistics["pairs"][requested] = pair_stats
                continue

            sessions = self._session_stats_from_hourly(sub)
            cov = coverage_df[coverage_df["pair"] == stored]
            coverage = {}
            if not cov.empty:
                r = cov.iloc[0]
                coverage = {
                    "distinct_days": int(r["distinct_days"]),
                    "first_ts": r["first_ts"],
                    "last_ts": r["last_ts"],
                }

            sub_bars = hourly_bars_df[hourly_bars_df["pair"] == stored] if not hourly_bars_df.empty else pd.DataFrame()
            hourly_breakdown = (
                self._enhanced_hourly_breakdown(sub_bars)
                if not sub_bars.empty
                else sub.to_dict(orient="records")
            )
            pair_stats["market_sessions_data"] = {
                "pair": stored,
                "days_analyzed": days_back if days_back is not None else "all",
                "sessions": sessions,
                "hourly_breakdown": hourly_breakdown,
                "coverage": coverage,
            }
            statistics["pairs"][requested] = pair_stats
            logger.info("✅ %s (stored as %s): volume computed.", requested, stored)

        statistics["summary"] = self._generate_summary(statistics["pairs"])

        cfg = tuning_config or TuningConfig()
        cache_params = cfg.load_cache(days_back, pairs) if tune_hyperparams and cfg.cache_path else None
        if cache_params:
            logger.info("  Cache hit: reusing tuned params for KMeans/IF where available")

        # ML 1/3: KMeans
        if not hourly_df.empty:
            logger.info("ML 1/3: Pair clusters (KMeans)%s", " — tuning n_clusters by silhouette" if tune_hyperparams else " — fixed n_clusters=3")
            cached_k = (cache_params or {}).get("kmeans", {}).get("n_clusters") if cache_params else None
            statistics["summary"]["pair_clusters"] = self._compute_pair_clusters(
                hourly_df,
                tune_k=tune_hyperparams and cached_k is None,
                n_clusters=cached_k,
                k_range=cfg.k_range,
                min_silhouette=cfg.min_silhouette,
                use_tslearn=cfg.use_tslearn_kmeans,
            )
            if tune_hyperparams and statistics["summary"].get("pair_clusters"):
                pc = statistics["summary"]["pair_clusters"]
                n_clusters = len(set(pc.values())) if pc else 3
                if cache_params is None:
                    cache_params = {}
                cache_params["kmeans"] = {"n_clusters": n_clusters}

        # ML 2/3: Isolation Forest (daily)
        daily_df = self._query_daily_totals(days_back)
        if_params: Dict[str, Dict[str, Any]] = {}
        if not daily_df.empty:
            logger.info("ML 2/3: Volume anomalies (Isolation Forest)%s", " — tuning contamination × n_estimators" if tune_hyperparams else " — fixed contamination=0.1")
            cache_if = (cache_params or {}).get("if", {}) if cache_params else None
            statistics["summary"]["volume_anomalies"] = self._compute_volume_anomalies(
                daily_df,
                tune=tune_hyperparams,
                tuning_config=cfg,
                cache_if=cache_if,
                out_if_params=if_params,
            )
            if tune_hyperparams and if_params:
                if cache_params is None:
                    cache_params = {}
                cache_params["if"] = if_params

        # Per-hour volume anomalies (Isolation Forest on hourly totals)
        hourly_totals_df = self._query_hourly_totals(days_back)
        if not hourly_totals_df.empty:
            logger.info("Per-hour volume anomalies (Isolation Forest on date-hour totals)%s", " — tuning" if tune_hyperparams else " — fixed")
            cache_if_hourly = (cache_params or {}).get("if_hourly", {}) if cache_params else None
            if_params_hourly: Dict[str, Dict[str, Any]] = {}
            statistics["summary"]["hourly_volume_anomalies"] = self._compute_hourly_volume_anomalies(
                hourly_totals_df,
                tune=tune_hyperparams,
                tuning_config=cfg,
                cache_if=cache_if_hourly,
                out_if_params=if_params_hourly,
            )
            if tune_hyperparams and if_params_hourly and cache_params is not None:
                cache_params["if_hourly"] = if_params_hourly

        # Volatility (ATR vs volume correlation) when OHLC available
        if getattr(self, "_has_ohlc", False):
            ohlcv_df = self._query_ohlcv(days_back)
            if not ohlcv_df.empty:
                statistics["summary"]["volatility_correlations"] = self._compute_volatility_correlations(ohlcv_df)

        # ML 3/3: ARIMA
        hourly_ts_df = self._query_hourly_timeseries(days_back)
        if not hourly_ts_df.empty:
            logger.info("ML 3/3: Hourly forecasts (ARIMA)%s", " — tuning order via auto_arima (seasonal m=%d)" % cfg.seasonal_period if tune_hyperparams else " — fixed order=(1,0,0)")
            statistics["summary"]["hourly_forecasts"] = self._compute_hourly_forecasts(
                hourly_ts_df,
                tune=tune_hyperparams,
                seasonal_period=cfg.seasonal_period,
                train_ratio=cfg.train_ratio,
                use_exog_dow=cfg.arima_use_exog_dow,
                log_test_mae=logger.isEnabledFor(logging.DEBUG),
                workers=cfg.workers,
            )

        if tune_hyperparams and cache_params and cfg.cache_path:
            cfg.save_cache(days_back, pairs, cache_params)

        return statistics

    def _generate_summary(self, pairs_data: Dict[str, Any]) -> Dict[str, Any]:
        """Summary stats. volume_distribution = per-session share of total volume."""
        summary: Dict[str, Any] = {
            "session_volume_rankings": [],
            "average_volumes_by_session": {},
            "volume_distribution": {},
        }

        session_totals: Dict[str, float] = defaultdict(float)
        session_counts: Dict[str, int] = defaultdict(int)

        for _req, data in pairs_data.items():
            ch = data.get("market_sessions_data")
            if not ch or not ch.get("sessions"):
                continue
            for sn, ss in ch["sessions"].items():
                v = ss.get("volume", 0) or 0
                if v > 0:
                    session_totals[sn] += v
                    session_counts[sn] += 1

        for sn in session_totals:
            c = session_counts[sn]
            tot = session_totals[sn]
            summary["average_volumes_by_session"][sn] = {
                "total_volume": tot,
                "pair_count": c,
                "average_per_pair": tot / c if c else 0,
            }

        sorted_sessions = sorted(
            summary["average_volumes_by_session"].items(),
            key=lambda x: x[1]["total_volume"],
            reverse=True,
        )
        summary["session_volume_rankings"] = [
            {"rank": i + 1, "session": name, "total_volume": s["total_volume"]}
            for i, (name, s) in enumerate(sorted_sessions)
        ]

        grand = sum(session_totals.values())
        if grand > 0:
            for sn, tot in session_totals.items():
                summary["volume_distribution"][sn] = {
                    "volume": tot,
                    "pct_of_total": round(100.0 * tot / grand, 2),
                }

        return summary

    def save_statistics(self, statistics: Dict[str, Any], output_path: str | Path) -> None:
        out = Path(output_path)
        with open(out, "w") as f:
            json.dump(statistics, f, indent=2, default=_json_default)
        logger.info("✅ Statistics saved to %s", out)

    def persist_ml_insights_to_clickhouse(self, statistics: Dict[str, Any], timeframe: str = "") -> None:
        """Insert ML outputs (KMeans, ARIMA, IF anomalies, volatility) into ClickHouse with run timestamp."""
        if not self._client:
            return
        raw_ts = statistics.get("generated_at")
        if not raw_ts:
            logger.warning("No generated_at in statistics; skipping ClickHouse ML persist.")
            return
        if isinstance(raw_ts, str):
            raw_ts = raw_ts.replace("Z", "+00:00")
        run_ts = datetime.fromisoformat(raw_ts)
        if run_ts.tzinfo is None:
            run_ts = run_ts.replace(tzinfo=timezone.utc)
        db = CLICKHOUSE_DATABASE
        summary = statistics.get("summary") or {}
        tf = timeframe or statistics.get("timeframe", "")

        # KMeans: pair_clusters {pair: cluster_id}
        pc = summary.get("pair_clusters") or {}
        if pc:
            df_pc = pd.DataFrame([
                {"pair": p, "timeframe": tf, "cluster_id": int(c), "generated_at": run_ts}
                for p, c in pc.items()
            ])
            self._client.insert_df(f"{db}.msv_pair_clusters", df_pc)
            logger.info("  Persisted %d pair_clusters (KMeans) to ClickHouse", len(df_pc))

        # ARIMA: hourly_forecasts {"pair|hour_gmt": {pair, hour_gmt, next_volume_forecast}}
        hf = summary.get("hourly_forecasts") or {}
        if hf:
            rows = []
            for _k, v in hf.items():
                if isinstance(v, dict) and "pair" in v and "hour_gmt" in v:
                    rows.append({
                        "pair": v["pair"],
                        "timeframe": tf,
                        "hour_gmt": int(v["hour_gmt"]),
                        "next_volume_forecast": _safe_float(v.get("next_volume_forecast")),
                        "generated_at": run_ts,
                    })
            if rows:
                df_hf = pd.DataFrame(rows)
                self._client.insert_df(f"{db}.msv_hourly_forecasts", df_hf)
                logger.info("  Persisted %d hourly_forecasts (ARIMA) to ClickHouse", len(df_hf))

        # Isolation Forest daily: volume_anomalies {pair: [{date, daily_volume, is_anomaly}, ...]}
        va = summary.get("volume_anomalies") or {}
        if va:
            rows = []
            for pair, recs in va.items():
                if not isinstance(recs, list):
                    continue
                for r in recs:
                    if not isinstance(r, dict):
                        continue
                    dt = r.get("date")
                    if dt is None:
                        continue
                    if isinstance(dt, str):
                        dt = pd.to_datetime(dt).date()
                    elif hasattr(dt, "date"):
                        dt = dt.date()
                    rows.append({
                        "pair": pair,
                        "timeframe": tf,
                        "date": dt,
                        "daily_volume": _safe_float(r.get("daily_volume")),
                        "is_anomaly": 1 if r.get("is_anomaly") else 0,
                        "generated_at": run_ts,
                    })
            if rows:
                df_va = pd.DataFrame(rows)
                self._client.insert_df(f"{db}.msv_volume_anomalies_daily", df_va)
                logger.info("  Persisted %d volume_anomalies (daily IF) to ClickHouse", len(df_va))

        # Isolation Forest hourly: hourly_volume_anomalies {pair: [{date, hour_gmt, hourly_volume, is_anomaly}, ...]}
        hva = summary.get("hourly_volume_anomalies") or {}
        if hva:
            rows = []
            for pair, recs in hva.items():
                if not isinstance(recs, list):
                    continue
                for r in recs:
                    if not isinstance(r, dict):
                        continue
                    dt = r.get("date")
                    if dt is None:
                        continue
                    if isinstance(dt, str):
                        dt = pd.to_datetime(dt).date()
                    elif hasattr(dt, "date"):
                        dt = dt.date()
                    rows.append({
                        "pair": pair,
                        "timeframe": tf,
                        "date": dt,
                        "hour_gmt": int(r.get("hour_gmt", 0)),
                        "hourly_volume": _safe_float(r.get("hourly_volume")),
                        "is_anomaly": 1 if r.get("is_anomaly") else 0,
                        "anomaly_score": _safe_float(r.get("anomaly_score", 0.0)),
                        "generated_at": run_ts,
                    })
            if rows:
                df_hva = pd.DataFrame(rows)
                self._client.insert_df(f"{db}.msv_volume_anomalies_hourly", df_hva)
                logger.info("  Persisted %d hourly_volume_anomalies to ClickHouse", len(df_hva))

        # Volatility: volatility_correlations {pair: correlation}
        vc = summary.get("volatility_correlations") or {}
        if vc:
            df_vc = pd.DataFrame([
                {"pair": p, "timeframe": tf, "correlation": _safe_float(c), "generated_at": run_ts}
                for p, c in vc.items()
            ])
            self._client.insert_df(f"{db}.msv_volatility_correlations", df_vc)
            logger.info("  Persisted %d volatility_correlations to ClickHouse", len(df_vc))

        logger.info("✅ ML insights persisted to ClickHouse (generated_at=%s)", run_ts.isoformat())

    @staticmethod
    def is_good_volume_moment(
        pair: str,
        hour_gmt: int,
        current_volume: float,
        stats: Dict[str, Any],
        hist_multiplier: float = 1.20,
        forecast_multiplier: float = 1.00,
        absolute_floor: float = 1000000.0
    ) -> bool:
        """
        Determines if the current volume indicates a good moment to trade for the specified pair and hour.
        Uses the combined approach: Yes if current_volume > max(historical_avg * hist_multiplier, forecast * forecast_multiplier, absolute_floor).
        """
        pair_data = stats.get("pairs", {}).get(pair, {}).get("market_sessions_data")
        if not pair_data:
            return False

        # Get historical average for the hour
        hist_row = next(
            (r for r in pair_data.get("hourly_breakdown", []) if r["hour_gmt"] == hour_gmt),
            None
        )
        if not hist_row or hist_row["bar_count"] == 0:
            return False
        hist_avg = hist_row["total_volume"] / hist_row["bar_count"]

        # Get ARIMA forecast
        forecast_key = f"{pair}|{hour_gmt}"
        forecast = stats.get("summary", {}).get("hourly_forecasts", {}).get(forecast_key, {}).get("next_volume_forecast", 0)

        # Compute the threshold
        threshold = max(
            hist_avg * hist_multiplier,
            forecast * forecast_multiplier,
            absolute_floor
        )

        return current_volume > threshold


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate volume statistics from ClickHouse (Oanda-backed).")
    ap.add_argument("--days", type=int, default=None, metavar="N", help="Limit to last N days (default: none = all data)")
    ap.add_argument("--extended-days", type=int, default=None, metavar="N", help="Use more days for retraining (overrides --days when set)")
    ap.add_argument("--output", type=str, default=None, help="Output JSON path (default: <script_dir>/volume_statistics.json)")
    ap.add_argument("--pairs", type=str, default=None, help="Comma-separated pairs (default: 10 majors)")
    ap.add_argument("--extra-pairs", type=str, default="", help="Comma-separated additional pairs to include")
    ap.add_argument("--no-tune", action="store_true", help="Disable hyperparameter tuning; use fixed KMeans k=3, IF contamination=0.1, ARIMA order=(1,0,0)")
    ap.add_argument("--k-range", type=str, default="2-10", metavar="MIN-MAX", help="KMeans n_clusters search range (default: 2-10)")
    ap.add_argument("--min-silhouette", type=float, default=0.3, help="Min silhouette threshold; below this use k=1 (default: 0.3)")
    ap.add_argument("--use-tslearn-kmeans", action="store_true", help="Use tslearn TimeSeriesKMeans (DTW) for clustering (if installable)")
    ap.add_argument("--contamination-grid", type=str, default="0.05,0.075,0.1,0.125,0.15", help="Isolation Forest contamination grid (comma-separated)")
    ap.add_argument("--use-optuna-if", action="store_true", help="Use Optuna for Isolation Forest tuning (if installable)")
    ap.add_argument("--seasonal-period", type=int, default=5, help="ARIMA seasonal period m (weekdays=5, default: 5)")
    ap.add_argument("--train-ratio", type=float, default=0.8, help="Hold-out train ratio for ARIMA validation (default: 0.8)")
    ap.add_argument("--cache", type=str, default=None, metavar="PATH", help="Path to cache tuned params (reused when config/data match)")
    ap.add_argument("--no-cache", action="store_true", help="Ignore cache even if --cache path exists")
    _default_workers = min(4, os.cpu_count() or 4)
    ap.add_argument("--workers", type=int, default=_default_workers, help="Parallel workers for ARIMA fits (default: min(4, cpu_count)=%d)" % _default_workers)
    args = ap.parse_args()

    if args.pairs:
        pairs = [p.strip().replace("/", "_") for p in args.pairs.split(",") if p.strip()]
    else:
        pairs = list(DEFAULT_PAIRS)
    extra = [p.strip().replace("/", "_") for p in args.extra_pairs.split(",") if p.strip()]
    for p in extra:
        if p and p not in pairs:
            pairs.append(p)

    output = args.output
    if not output:
        output = Path(__file__).resolve().parent / "volume_statistics.json"

    try:
        k_min, k_max = _parse_k_range(args.k_range)
    except (ValueError, AttributeError):
        k_min, k_max = 2, 10
    try:
        contamination_grid = _parse_float_list(args.contamination_grid)
    except (ValueError, TypeError):
        contamination_grid = (0.05, 0.075, 0.1, 0.125, 0.15)
    cache_path = None
    if args.cache and not args.no_cache:
        cache_path = Path(args.cache)

    tuning_config = TuningConfig(
        k_range=(k_min, k_max),
        min_silhouette=args.min_silhouette,
        use_tslearn_kmeans=args.use_tslearn_kmeans,
        contamination_grid=contamination_grid,
        use_optuna_if=args.use_optuna_if,
        seasonal_period=args.seasonal_period,
        train_ratio=args.train_ratio,
        cache_path=cache_path,
        workers=args.workers,
    )

    days_back = args.extended_days if args.extended_days is not None else args.days
    gen = VolumeStatisticsGenerator()
    logger.info("🚀 Generating volume statistics (multi-pair query, non-overlapping sessions)")
    logger.info("Pairs: %s | Days: %s | Output: %s", pairs, days_back if days_back is not None else "all", output)
    logger.info("Tuning: k_range=%s, min_silhouette=%.2f, seasonal_period=%d, train_ratio=%.2f, workers=%d", args.k_range, args.min_silhouette, args.seasonal_period, args.train_ratio, args.workers)
    try:
        stats = gen.generate_session_statistics(
            pairs,
            days_back=days_back,
            tune_hyperparams=not args.no_tune,
            tuning_config=tuning_config,
        )
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)

    gen.save_statistics(stats, output)
    gen.persist_ml_insights_to_clickhouse(stats)

    summary = stats.get("summary") or {}
    rankings = summary.get("session_volume_rankings") or []
    if rankings:
        logger.info("Session volume rankings:")
        for r in rankings:
            logger.info("  %d. %s: %s", r["rank"], r["session"], r["total_volume"])
    dist = summary.get("volume_distribution") or {}
    if dist:
        logger.info("Volume distribution (%% of total): %s", {k: f"{v['pct_of_total']}%" for k, v in dist.items()})

    logger.info("✅ Done. Output: %s", output)


if __name__ == "__main__":
    main()
