"""Unit tests for event_scorer module."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from economic_calendar_agent.correlation import event_scorer
from economic_calendar_agent.models.events import EconomicEvent
from economic_calendar_agent.models.schemas import ImpactLevel, MacroRiskLevel


@pytest.fixture
def sample_event():
    """Create a sample economic event."""
    return EconomicEvent(
        event_id="test-1",
        event_name="Non-Farm Payrolls",
        event_type="NFP",
        country="US",
        currency="USD",
        event_datetime=datetime.now(timezone.utc),
        impact=ImpactLevel.HIGH,
        actual=250000.0,
        estimate=200000.0,
        previous=180000.0,
    )


@pytest.fixture
def future_event():
    """Create a future economic event."""
    return EconomicEvent(
        event_id="test-2",
        event_name="FOMC Rate Decision",
        event_type="FOMC",
        country="US",
        currency="USD",
        event_datetime=datetime.now(timezone.utc) + timedelta(hours=2),
        impact=ImpactLevel.HIGH,
        estimate=5.25,
        previous=5.00,
    )


def test_score_event_with_surprise(sample_event):
    """Test scoring event with actual surprise data."""
    pairs = ["USDJPY", "EURUSD", "GBPUSD", "AUDUSD"]

    scored = event_scorer.score_event(
        event=sample_event,
        pairs=pairs,
        historical_std=20000.0,  # Std dev of NFP surprises
    )

    # Check basic fields
    assert scored.event == sample_event
    assert scored.surprise_zscore is not None
    assert scored.surprise_zscore > 0  # Actual > Estimate

    # Check relevance scores
    assert len(scored.relevance_scores) == 4
    assert scored.relevance_scores["USDJPY"] == 0.95  # NFP relevance to USDJPY

    # Check composite scores exist for all pairs
    assert len(scored.composite_scores) == 4
    assert all(score >= 0 for score in scored.composite_scores.values())


def test_score_event_future_event(future_event):
    """Test scoring future event without actual data."""
    pairs = ["USDJPY", "EURUSD"]

    scored = event_scorer.score_event(
        event=future_event,
        pairs=pairs,
    )

    # No surprise data yet
    assert scored.surprise_zscore is None
    assert scored.surprise_direction is None
    assert scored.minutes_since_release is None

    # But should still have relevance and composite scores
    assert len(scored.relevance_scores) == 2
    assert scored.relevance_scores["USDJPY"] == 0.98  # FOMC relevance

    # Composite score should be non-zero (no decay, no surprise multiplier)
    assert scored.composite_scores["USDJPY"] > 0


def test_score_event_time_decay():
    """Test time decay in scoring."""
    # Create event 60 minutes ago
    past_event = EconomicEvent(
        event_id="test-3",
        event_name="CPI",
        event_type="CPI",
        country="US",
        currency="USD",
        event_datetime=datetime.now(timezone.utc) - timedelta(minutes=60),
        impact=ImpactLevel.HIGH,
        actual=3.5,
        estimate=3.0,
        previous=2.8,
    )

    pairs = ["USDJPY"]
    scored = event_scorer.score_event(
        event=past_event,
        pairs=pairs,
        historical_std=0.5,
    )

    # Time decay should be applied (< 1.0)
    assert 0 < scored.time_decay_factor < 1.0

    # Composite score should be reduced by decay
    # Formula: relevance × impact_weight × |surprise| × decay
    # CPI relevance to USDJPY = 0.90, impact_weight = 1.0 (HIGH)
    # Surprise = (3.5 - 3.0) / 0.5 = 1.0, decay < 1.0
    # So composite should be less than 0.90
    assert scored.composite_scores["USDJPY"] < 0.90


def test_score_upcoming_events():
    """Test scoring multiple upcoming events."""
    events = [
        EconomicEvent(
            event_id="e1",
            event_name="NFP",
            event_type="NFP",
            country="US",
            currency="USD",
            event_datetime=datetime.now(timezone.utc) + timedelta(hours=1),
            impact=ImpactLevel.HIGH,
        ),
        EconomicEvent(
            event_id="e2",
            event_name="CPI",
            event_type="CPI",
            country="US",
            currency="USD",
            event_datetime=datetime.now(timezone.utc) + timedelta(hours=6),
            impact=ImpactLevel.MEDIUM,
        ),
    ]

    pairs = ["USDJPY", "EURUSD"]
    scored_events = event_scorer.score_upcoming_events(events, pairs)

    assert len(scored_events) == 2
    assert all(isinstance(se.event, EconomicEvent) for se in scored_events)
    assert all(len(se.composite_scores) == 2 for se in scored_events)


def test_aggregate_macro_risk_high():
    """Test HIGH risk aggregation."""
    # Create high impact event within 30 min
    high_impact_event = EconomicEvent(
        event_id="high-1",
        event_name="FOMC",
        event_type="FOMC",
        country="US",
        currency="USD",
        event_datetime=datetime.now(timezone.utc) + timedelta(minutes=15),
        impact=ImpactLevel.HIGH,
    )

    pairs = ["USDJPY"]
    scored = event_scorer.score_event(high_impact_event, pairs)

    # Force high composite score and set minutes_since_release
    scored.composite_scores["USDJPY"] = 0.85
    scored.minutes_since_release = -15  # 15 minutes until release

    risk_levels = event_scorer.aggregate_macro_risk([scored], pairs)

    assert risk_levels["USDJPY"] == MacroRiskLevel.HIGH


def test_aggregate_macro_risk_medium():
    """Test MEDIUM risk aggregation."""
    # Create multiple medium events
    events = []
    for i in range(3):
        event = EconomicEvent(
            event_id=f"med-{i}",
            event_name=f"Event {i}",
            event_type="CPI",
            country="US",
            currency="USD",
            event_datetime=datetime.now(timezone.utc) + timedelta(hours=1),
            impact=ImpactLevel.MEDIUM,
        )
        events.append(event)

    pairs = ["USDJPY"]
    scored_events = event_scorer.score_upcoming_events(events, pairs)

    # Manually set scores to trigger MEDIUM (sum > 1.5)
    for scored in scored_events:
        scored.composite_scores["USDJPY"] = 0.6  # 3 * 0.6 = 1.8 > 1.5

    risk_levels = event_scorer.aggregate_macro_risk(scored_events, pairs)

    assert risk_levels["USDJPY"] == MacroRiskLevel.MEDIUM


def test_aggregate_macro_risk_low():
    """Test LOW risk aggregation."""
    # Create low impact event far in future
    low_event = EconomicEvent(
        event_id="low-1",
        event_name="Minor Event",
        event_type="RETAIL_SALES",
        country="US",
        currency="USD",
        event_datetime=datetime.now(timezone.utc) + timedelta(days=2),
        impact=ImpactLevel.LOW,
    )

    pairs = ["USDJPY"]
    scored = event_scorer.score_event(low_event, pairs)

    risk_levels = event_scorer.aggregate_macro_risk([scored], pairs)

    assert risk_levels["USDJPY"] == MacroRiskLevel.LOW


def test_format_for_llm():
    """Test formatting events for LLM consumption."""
    event = EconomicEvent(
        event_id="fmt-1",
        event_name="Non-Farm Payrolls",
        event_type="NFP",
        country="US",
        currency="USD",
        event_datetime=datetime.now(timezone.utc) + timedelta(hours=1),
        impact=ImpactLevel.HIGH,
        estimate=200000.0,
        previous=180000.0,
    )

    pairs = ["USDJPY", "EURUSD"]
    scored = event_scorer.score_event(event, pairs)

    formatted = event_scorer.format_for_llm([scored], pairs)

    # Check output contains expected sections
    assert "# Economic Calendar Analysis" in formatted
    assert "📅 Upcoming Events" in formatted
    assert "Non-Farm Payrolls" in formatted
    assert "⚡ Trading Implications" in formatted
    assert "USDJPY" in formatted


def test_format_for_llm_empty():
    """Test formatting with no events."""
    formatted = event_scorer.format_for_llm([], [])

    assert "No economic events" in formatted
