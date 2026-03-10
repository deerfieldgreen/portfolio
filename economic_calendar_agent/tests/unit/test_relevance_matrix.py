"""Unit tests for relevance_matrix module."""
from __future__ import annotations

import pytest

from economic_calendar_agent.correlation import relevance_matrix


def test_get_relevance_known_event():
    """Test getting relevance for known event types."""
    # FOMC should have high relevance to USDJPY
    score = relevance_matrix.get_relevance("FOMC", "USDJPY")
    assert score == 0.98

    # NFP should have high relevance to USDJPY
    score = relevance_matrix.get_relevance("NFP", "USDJPY")
    assert score == 0.95


def test_get_relevance_unknown_event():
    """Test getting relevance for unknown event returns 0.0."""
    score = relevance_matrix.get_relevance("UNKNOWN_EVENT", "USDJPY")
    assert score == 0.0


def test_get_relevance_unknown_pair():
    """Test getting relevance for unknown pair returns 0.0."""
    score = relevance_matrix.get_relevance("FOMC", "UNKNOWN_PAIR")
    assert score == 0.0


def test_normalize_event_name_direct_match():
    """Test normalizing event names with direct matches."""
    assert relevance_matrix.normalize_event_name("Non-Farm Payrolls") == "NFP"
    assert relevance_matrix.normalize_event_name("nfp") == "NFP"
    assert relevance_matrix.normalize_event_name("FOMC") == "FOMC"


def test_normalize_event_name_with_country():
    """Test normalizing event names with country context."""
    # US CPI should return just "CPI"
    assert relevance_matrix.normalize_event_name("Consumer Price Index", "US") == "CPI"

    # EU CPI should return "EU_CPI"
    assert relevance_matrix.normalize_event_name("Consumer Price Index", "EU") == "EU_CPI"

    # Central bank events should not get country prefix
    assert relevance_matrix.normalize_event_name("ECB", "EU") == "ECB"


def test_normalize_event_name_partial_match():
    """Test partial matching in event names."""
    assert "CPI" in relevance_matrix.normalize_event_name("Inflation Rate YoY")
    assert "GDP" in relevance_matrix.normalize_event_name("GDP Growth Rate QoQ")


def test_get_affected_pairs():
    """Test getting affected pairs above threshold."""
    pairs = relevance_matrix.get_affected_pairs("FOMC", min_score=0.7)

    # Should return all 4 pairs (all above 0.7)
    assert len(pairs) == 4

    # Should be sorted by score descending
    assert pairs[0][0] == "USDJPY"
    assert pairs[0][1] == 0.98

    # Test with higher threshold
    pairs = relevance_matrix.get_affected_pairs("FOMC", min_score=0.9)
    assert len(pairs) == 3  # Only USDJPY, EURUSD, GBPUSD


def test_get_affected_pairs_empty():
    """Test getting affected pairs for unknown event returns empty list."""
    pairs = relevance_matrix.get_affected_pairs("UNKNOWN_EVENT")
    assert pairs == []


def test_get_all_event_types():
    """Test getting all canonical event types."""
    event_types = relevance_matrix.get_all_event_types()

    assert "FOMC" in event_types
    assert "NFP" in event_types
    assert "ECB" in event_types
    assert "RBA" in event_types


def test_load_relevance_overrides():
    """Test loading dynamic relevance overrides."""
    # Load custom override
    overrides = {
        "NEW_EVENT": {
            "USDJPY": 0.85,
            "EURUSD": 0.75,
        }
    }

    relevance_matrix.load_relevance_overrides(overrides)

    # Check override was applied
    assert relevance_matrix.get_relevance("NEW_EVENT", "USDJPY") == 0.85
    assert relevance_matrix.get_relevance("NEW_EVENT", "EURUSD") == 0.75


def test_relevance_scores_range():
    """Test that all relevance scores are in valid range [0, 1]."""
    event_types = relevance_matrix.get_all_event_types()
    pairs = ["USDJPY", "EURUSD", "GBPUSD", "AUDUSD"]

    for event_type in event_types:
        for pair in pairs:
            score = relevance_matrix.get_relevance(event_type, pair)
            assert 0.0 <= score <= 1.0, f"Invalid score for {event_type} × {pair}: {score}"
