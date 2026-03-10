"""Surprise factor calculation using z-scores.

Computes standardized surprise: (Actual - Forecast) / σ_historical
Based on ECB Working Paper 1150 (2010) surprise index methodology.
"""
from __future__ import annotations

from typing import Optional

from ..models.schemas import SurpriseDirection


def compute_surprise_zscore(
    actual: float,
    forecast: float,
    historical_std: float,
) -> float:
    """Compute z-score surprise for an economic release.

    Args:
        actual: Actual released value
        forecast: Consensus forecast
        historical_std: Historical standard deviation of surprises

    Returns:
        Z-score surprise (positive = beat forecast, negative = miss)
    """
    if historical_std <= 0:
        return 0.0  # Can't compute surprise without variance

    surprise = actual - forecast
    z_score = surprise / historical_std
    return z_score


def classify_surprise(zscore: float) -> SurpriseDirection:
    """Classify surprise magnitude into categorical bins.

    Thresholds based on standard statistical significance:
    - |z| > 2.0 = ~95% confidence, "large" surprise
    - |z| > 1.0 = ~68% confidence, "notable" surprise
    - |z| <= 1.0 = "inline" with expectations

    Args:
        zscore: Surprise z-score

    Returns:
        SurpriseDirection enum
    """
    if zscore > 2.0:
        return SurpriseDirection.LARGE_POSITIVE
    elif zscore > 1.0:
        return SurpriseDirection.POSITIVE
    elif zscore < -2.0:
        return SurpriseDirection.LARGE_NEGATIVE
    elif zscore < -1.0:
        return SurpriseDirection.NEGATIVE
    else:
        return SurpriseDirection.INLINE


def compute_absolute_surprise_magnitude(
    actual: float,
    forecast: float,
) -> float:
    """Compute absolute percentage surprise.

    Args:
        actual: Actual released value
        forecast: Consensus forecast

    Returns:
        Absolute percentage difference
    """
    if forecast == 0:
        return 0.0  # Avoid division by zero

    return abs((actual - forecast) / forecast) * 100.0


def compute_citi_style_weighted_surprise(
    surprises: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Compute Citi-style weighted surprise index.

    Combines multiple indicator surprises weighted by their empirical
    FX impact sensitivity (calibrated from historical data).

    Args:
        surprises: Dict of indicator -> z-score surprise
        weights: Dict of indicator -> FX impact weight

    Returns:
        Weighted composite surprise score
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(
        surprises.get(indicator, 0.0) * weight
        for indicator, weight in weights.items()
    )

    return weighted_sum / total_weight


def get_expected_surprise_magnitude(
    historical_std: float,
    confidence_level: float = 0.68,
) -> float:
    """Get expected surprise magnitude for unreleased events.

    For upcoming events (no actual value yet), estimate the likely
    surprise magnitude based on historical volatility.

    Args:
        historical_std: Historical standard deviation of surprises
        confidence_level: Confidence interval (default 68% = ±1σ)

    Returns:
        Expected absolute z-score magnitude
    """
    # For 68% confidence, expected |z| ≈ 1.0
    # For 95% confidence, expected |z| ≈ 2.0
    if confidence_level >= 0.95:
        return 2.0
    elif confidence_level >= 0.68:
        return 1.0
    else:
        return 0.5
