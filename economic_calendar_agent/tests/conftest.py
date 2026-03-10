"""Pytest fixtures for economic calendar agent tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from economic_calendar_agent.models.events import EconomicEvent
from economic_calendar_agent.models.schemas import ImpactLevel


@pytest.fixture
def sample_nfp_event():
    """Sample Non-Farm Payrolls event."""
    return EconomicEvent(
        event_id="nfp-test-1",
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
def sample_cpi_event():
    """Sample CPI event."""
    return EconomicEvent(
        event_id="cpi-test-1",
        event_name="Consumer Price Index",
        event_type="CPI",
        country="US",
        currency="USD",
        event_datetime=datetime.now(timezone.utc),
        impact=ImpactLevel.HIGH,
        actual=3.5,
        estimate=3.2,
        previous=3.0,
    )


@pytest.fixture
def sample_fomc_event():
    """Sample FOMC event."""
    return EconomicEvent(
        event_id="fomc-test-1",
        event_name="FOMC Rate Decision",
        event_type="FOMC",
        country="US",
        currency="USD",
        event_datetime=datetime.now(timezone.utc),
        impact=ImpactLevel.HIGH,
        actual=5.50,
        estimate=5.25,
        previous=5.25,
    )


@pytest.fixture
def sample_pairs():
    """Standard FX pairs for testing."""
    return ["USDJPY", "EURUSD", "GBPUSD", "AUDUSD"]


@pytest.fixture
def mock_fmp_calendar_response():
    """Mock FMP economic calendar API response."""
    return [
        {
            "event": "Non-Farm Payrolls",
            "date": "2025-02-07 13:30:00",
            "country": "US",
            "currency": "USD",
            "impact": "High",
            "actual": 250000,
            "estimate": 200000,
            "previous": 180000,
        },
        {
            "event": "Consumer Price Index YoY",
            "date": "2025-02-14 13:30:00",
            "country": "US",
            "currency": "USD",
            "impact": "High",
            "actual": None,  # Future event
            "estimate": 3.2,
            "previous": 3.0,
        },
    ]


@pytest.fixture
def mock_historical_std():
    """Mock historical standard deviations for events."""
    return {
        "NFP": 20000.0,
        "CPI": 0.3,
        "GDP": 0.5,
        "FOMC": 0.25,
    }
