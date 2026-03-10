"""Unit tests for fx_pair_map module."""
from __future__ import annotations

import pytest

from economic_calendar_agent.data import fx_pair_map


def test_get_affected_pairs_us():
    """Test US events affect all pairs."""
    pairs = fx_pair_map.get_affected_pairs("US")

    assert "USDJPY" in pairs
    assert "EURUSD" in pairs
    assert "GBPUSD" in pairs
    assert "AUDUSD" in pairs


def test_get_affected_pairs_jp():
    """Test JP events affect USDJPY."""
    pairs = fx_pair_map.get_affected_pairs("JP")

    assert "USDJPY" in pairs
    assert len(pairs) == 1


def test_get_affected_pairs_eu():
    """Test EU events affect EURUSD."""
    pairs = fx_pair_map.get_affected_pairs("EU")

    assert "EURUSD" in pairs


def test_get_affected_pairs_unknown():
    """Test unknown country returns empty list."""
    pairs = fx_pair_map.get_affected_pairs("UNKNOWN")

    assert pairs == []


def test_get_pair_countries():
    """Test getting countries for a pair."""
    countries = fx_pair_map.get_pair_countries("USDJPY")

    assert "US" in countries
    assert "JP" in countries


def test_get_pair_countries_audusd():
    """Test AUDUSD includes China (commodity linkage)."""
    countries = fx_pair_map.get_pair_countries("AUDUSD")

    assert "US" in countries
    assert "AU" in countries
    assert "CN" in countries


def test_get_pair_countries_unknown():
    """Test unknown pair returns empty list."""
    countries = fx_pair_map.get_pair_countries("UNKNOWN")

    assert countries == []


def test_get_central_banks():
    """Test getting central banks for a pair."""
    banks = fx_pair_map.get_central_banks("USDJPY")

    assert "Fed" in banks or "FOMC" in banks
    assert "BOJ" in banks


def test_is_usd_event():
    """Test identifying USD events."""
    assert fx_pair_map.is_usd_event("US") is True
    assert fx_pair_map.is_usd_event("USA") is True
    assert fx_pair_map.is_usd_event("JP") is False
    assert fx_pair_map.is_usd_event("EU") is False


def test_is_central_bank_event():
    """Test identifying central bank events."""
    assert fx_pair_map.is_central_bank_event("FOMC") is True
    assert fx_pair_map.is_central_bank_event("ECB") is True
    assert fx_pair_map.is_central_bank_event("BOE") is True
    assert fx_pair_map.is_central_bank_event("RBA") is True
    assert fx_pair_map.is_central_bank_event("BOJ") is True
    assert fx_pair_map.is_central_bank_event("Fed") is True

    assert fx_pair_map.is_central_bank_event("NFP") is False
    assert fx_pair_map.is_central_bank_event("CPI") is False


def test_get_all_pairs():
    """Test getting all configured pairs."""
    pairs = fx_pair_map.get_all_pairs()

    assert len(pairs) == 4
    assert "USDJPY" in pairs
    assert "EURUSD" in pairs
    assert "GBPUSD" in pairs
    assert "AUDUSD" in pairs


def test_get_pair_symbol():
    """Test splitting pair into base and quote."""
    base, quote = fx_pair_map.get_pair_symbol("USDJPY")

    assert base == "USD"
    assert quote == "JPY"


def test_get_pair_symbol_lowercase():
    """Test pair symbol with lowercase input."""
    base, quote = fx_pair_map.get_pair_symbol("eurusd")

    assert base == "EUR"
    assert quote == "USD"


def test_get_pair_symbol_invalid():
    """Test invalid pair format raises error."""
    with pytest.raises(ValueError, match="Invalid FX pair format"):
        fx_pair_map.get_pair_symbol("INVALID")
