"""Unit tests for time_decay module."""
from __future__ import annotations

import pytest

from economic_calendar_agent.correlation import time_decay
from economic_calendar_agent.models.events import DecayParams


def test_get_decay_params_known_event():
    """Test getting decay params for known event types."""
    params = time_decay.get_decay_params("FOMC")

    assert params.event_type == "FOMC"
    assert params.fast_halflife_minutes == 10.0
    assert params.slow_halflife_minutes == 240.0
    assert params.alpha == 0.40


def test_get_decay_params_unknown_event():
    """Test getting decay params for unknown event returns default."""
    params = time_decay.get_decay_params("UNKNOWN_EVENT")

    assert params.event_type == "_DEFAULT"
    assert params.fast_halflife_minutes == 5.0
    assert params.slow_halflife_minutes == 60.0
    assert params.alpha == 0.50


def test_compute_decay_no_time_elapsed():
    """Test decay with zero time elapsed returns initial impact."""
    impact = time_decay.compute_decay(
        impact_initial=100.0,
        event_type="NFP",
        minutes_elapsed=0.0,
    )
    assert impact == pytest.approx(100.0)


def test_compute_decay_at_fast_halflife():
    """Test decay at fast component half-life."""
    params = time_decay.get_decay_params("NFP")

    # At fast half-life (5 min), fast component should be ~50%
    # But total impact depends on both components
    impact = time_decay.compute_decay(
        impact_initial=100.0,
        event_type="NFP",
        minutes_elapsed=params.fast_halflife_minutes,
    )

    # With alpha=0.6, fast component: 0.6 * 100 * 0.5 = 30
    # Slow component at 5 min (half-life=60): 0.4 * 100 * e^(-ln(2)*5/60) ≈ 38.6
    # Total ≈ 68.6
    assert 60.0 < impact < 80.0


def test_compute_decay_future_event():
    """Test decay for future events (negative time) returns initial impact."""
    impact = time_decay.compute_decay(
        impact_initial=100.0,
        event_type="NFP",
        minutes_elapsed=-10.0,
    )
    assert impact == 100.0


def test_compute_decay_long_elapsed():
    """Test decay after long time approaches zero."""
    # After 10 hours (600 min)
    impact = time_decay.compute_decay(
        impact_initial=100.0,
        event_type="NFP",
        minutes_elapsed=600.0,
    )

    # Should be very small (both components decayed)
    assert impact < 1.0


def test_remaining_impact_pct():
    """Test calculating remaining impact percentage."""
    # At t=0, should be 100%
    pct = time_decay.remaining_impact_pct("NFP", 0.0)
    assert pct == pytest.approx(1.0)

    # At slow half-life (60 min for NFP)
    pct = time_decay.remaining_impact_pct("NFP", 60.0)
    # Should be between 0.2 and 0.5 (both components decayed)
    assert 0.2 < pct < 0.5


def test_remaining_impact_pct_monotonic():
    """Test that remaining impact decreases monotonically."""
    times = [0.0, 5.0, 10.0, 30.0, 60.0, 120.0]
    impacts = [time_decay.remaining_impact_pct("FOMC", t) for t in times]

    # Each should be smaller than previous
    for i in range(1, len(impacts)):
        assert impacts[i] < impacts[i - 1], f"Impact not monotonic: {impacts}"


def test_minutes_until_threshold():
    """Test calculating time until threshold."""
    # Time until 10% of initial impact
    minutes = time_decay.minutes_until_threshold("NFP", threshold_pct=0.1)

    # Should be positive
    assert minutes > 0

    # Verify impact is actually below threshold
    impact = time_decay.remaining_impact_pct("NFP", minutes)
    assert impact <= 0.1


def test_minutes_until_threshold_50_pct():
    """Test time until 50% threshold approximates half-life."""
    minutes = time_decay.minutes_until_threshold("NFP", threshold_pct=0.5)

    # With alpha=0.6 (fast dominant, 5min half-life) and slow (60min), 
    # 50% threshold is reached much faster due to fast component weight
    # Expect somewhere between fast and slow half-lives
    assert 5.0 < minutes < 30.0


def test_decay_params_validation():
    """Test DecayParams validation."""
    # Valid params should work
    params = DecayParams(
        event_type="TEST",
        fast_halflife_minutes=5.0,
        slow_halflife_minutes=60.0,
        alpha=0.5,
    )
    assert params.alpha == 0.5

    # Invalid alpha should raise
    with pytest.raises(ValueError, match="alpha must be in"):
        DecayParams(
            event_type="TEST",
            fast_halflife_minutes=5.0,
            slow_halflife_minutes=60.0,
            alpha=1.5,
        )

    # Invalid half-life should raise
    with pytest.raises(ValueError, match="fast_halflife_minutes must be"):
        DecayParams(
            event_type="TEST",
            fast_halflife_minutes=-5.0,
            slow_halflife_minutes=60.0,
            alpha=0.5,
        )


def test_load_decay_overrides():
    """Test loading custom decay parameters."""
    custom_params = DecayParams(
        event_type="CUSTOM_EVENT",
        fast_halflife_minutes=3.0,
        slow_halflife_minutes=30.0,
        alpha=0.7,
    )

    time_decay.load_decay_overrides({"CUSTOM_EVENT": custom_params})

    # Retrieve and verify
    loaded = time_decay.get_decay_params("CUSTOM_EVENT")
    assert loaded.fast_halflife_minutes == 3.0
    assert loaded.slow_halflife_minutes == 30.0
    assert loaded.alpha == 0.7
