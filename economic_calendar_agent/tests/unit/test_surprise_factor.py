"""Unit tests for surprise_factor module."""
from __future__ import annotations

import pytest

from economic_calendar_agent.correlation import surprise_factor
from economic_calendar_agent.models.schemas import SurpriseDirection


def test_compute_surprise_zscore_positive():
    """Test computing positive surprise z-score."""
    # Actual beats forecast by 1 standard deviation
    zscore = surprise_factor.compute_surprise_zscore(
        actual=105.0,
        forecast=100.0,
        historical_std=5.0,
    )
    assert zscore == 1.0


def test_compute_surprise_zscore_negative():
    """Test computing negative surprise z-score."""
    # Actual misses forecast by 2 standard deviations
    zscore = surprise_factor.compute_surprise_zscore(
        actual=90.0,
        forecast=100.0,
        historical_std=5.0,
    )
    assert zscore == -2.0


def test_compute_surprise_zscore_inline():
    """Test computing inline surprise (actual = forecast)."""
    zscore = surprise_factor.compute_surprise_zscore(
        actual=100.0,
        forecast=100.0,
        historical_std=5.0,
    )
    assert zscore == 0.0


def test_compute_surprise_zscore_zero_std():
    """Test computing surprise with zero std dev returns 0."""
    zscore = surprise_factor.compute_surprise_zscore(
        actual=105.0,
        forecast=100.0,
        historical_std=0.0,
    )
    assert zscore == 0.0


def test_classify_surprise_large_positive():
    """Test classifying large positive surprise."""
    direction = surprise_factor.classify_surprise(2.5)
    assert direction == SurpriseDirection.LARGE_POSITIVE


def test_classify_surprise_positive():
    """Test classifying moderate positive surprise."""
    direction = surprise_factor.classify_surprise(1.5)
    assert direction == SurpriseDirection.POSITIVE


def test_classify_surprise_inline():
    """Test classifying inline surprise."""
    direction = surprise_factor.classify_surprise(0.5)
    assert direction == SurpriseDirection.INLINE

    direction = surprise_factor.classify_surprise(-0.5)
    assert direction == SurpriseDirection.INLINE


def test_classify_surprise_negative():
    """Test classifying moderate negative surprise."""
    direction = surprise_factor.classify_surprise(-1.5)
    assert direction == SurpriseDirection.NEGATIVE


def test_classify_surprise_large_negative():
    """Test classifying large negative surprise."""
    direction = surprise_factor.classify_surprise(-2.5)
    assert direction == SurpriseDirection.LARGE_NEGATIVE


def test_classify_surprise_boundary():
    """Test boundary conditions for surprise classification."""
    # Exactly at thresholds
    assert surprise_factor.classify_surprise(2.0) == SurpriseDirection.POSITIVE
    assert surprise_factor.classify_surprise(1.0) == SurpriseDirection.INLINE
    assert surprise_factor.classify_surprise(-1.0) == SurpriseDirection.INLINE
    assert surprise_factor.classify_surprise(-2.0) == SurpriseDirection.NEGATIVE


def test_compute_absolute_surprise_magnitude():
    """Test computing absolute percentage surprise."""
    # 10% beat
    magnitude = surprise_factor.compute_absolute_surprise_magnitude(
        actual=110.0,
        forecast=100.0,
    )
    assert magnitude == 10.0

    # 5% miss
    magnitude = surprise_factor.compute_absolute_surprise_magnitude(
        actual=95.0,
        forecast=100.0,
    )
    assert magnitude == 5.0


def test_compute_absolute_surprise_magnitude_zero_forecast():
    """Test absolute surprise with zero forecast returns 0."""
    magnitude = surprise_factor.compute_absolute_surprise_magnitude(
        actual=10.0,
        forecast=0.0,
    )
    assert magnitude == 0.0


def test_compute_citi_style_weighted_surprise():
    """Test Citi-style weighted surprise index."""
    surprises = {
        "NFP": 2.0,
        "CPI": 1.0,
        "GDP": -0.5,
    }

    weights = {
        "NFP": 0.5,
        "CPI": 0.3,
        "GDP": 0.2,
    }

    weighted = surprise_factor.compute_citi_style_weighted_surprise(surprises, weights)

    # Expected: (2.0 * 0.5 + 1.0 * 0.3 + -0.5 * 0.2) / 1.0 = 1.2
    assert weighted == pytest.approx(1.2)


def test_compute_citi_style_weighted_surprise_zero_weight():
    """Test weighted surprise with zero total weight returns 0."""
    surprises = {"NFP": 2.0}
    weights = {}

    weighted = surprise_factor.compute_citi_style_weighted_surprise(surprises, weights)
    assert weighted == 0.0


def test_get_expected_surprise_magnitude():
    """Test expected surprise magnitude for unreleased events."""
    # 68% confidence should return ~1.0
    expected = surprise_factor.get_expected_surprise_magnitude(
        historical_std=5.0,
        confidence_level=0.68,
    )
    assert expected == 1.0

    # 95% confidence should return ~2.0
    expected = surprise_factor.get_expected_surprise_magnitude(
        historical_std=5.0,
        confidence_level=0.95,
    )
    assert expected == 2.0
