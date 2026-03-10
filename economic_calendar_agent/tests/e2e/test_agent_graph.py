"""End-to-end tests for agent graph execution.

Tests the full agent graph with mocked backends.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from economic_calendar_agent.agent.graph import build_graph
from economic_calendar_agent.agent.state import FXTradingState
from economic_calendar_agent.models.schemas import EconomicContext, MacroRiskLevel


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("economic_calendar_agent.agent.orchestrator.get_settings") as mock:
        settings = MagicMock()
        settings.llm_model = "gpt-4o-mini"
        settings.llm_temperature = 0.1
        settings.llm_max_tokens = 500
        settings.llm_api_key = None
        settings.target_pairs = ["USDJPY", "EURUSD"]
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_economic_context():
    """Mock economic context data."""
    return EconomicContext(
        events=[],
        macro_risk={"USDJPY": MacroRiskLevel.LOW, "EURUSD": MacroRiskLevel.LOW},
        high_impact_imminent=[],
        summary="No significant economic events in the next 48 hours.",
    )


@pytest.mark.asyncio
async def test_graph_builds_successfully():
    """Test that graph can be built without errors."""
    graph = build_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_economic_node_execution(mock_settings, mock_economic_context):
    """Test economic calendar node executes and returns context."""
    with patch(
        "economic_calendar_agent.agent.nodes.economic.FMPClient"
    ) as mock_fmp, patch(
        "economic_calendar_agent.agent.nodes.economic.RedisCache"
    ) as mock_redis:
        # Mock FMP client
        fmp_instance = mock_fmp.return_value
        fmp_instance.fetch_upcoming_events = AsyncMock(return_value=[])
        fmp_instance.close = AsyncMock()

        # Mock Redis cache
        redis_instance = mock_redis.return_value
        redis_instance.get_json = AsyncMock(return_value=None)
        redis_instance.set_json = AsyncMock()
        redis_instance.disconnect = AsyncMock()

        # Import and call node
        from economic_calendar_agent.agent.nodes.economic import (
            economic_calendar_node,
        )

        initial_state: FXTradingState = {
            "messages": [],
            "economic_context": None,
            "technical_signals": None,
            "sentiment_scores": None,
            "risk_assessment": None,
            "target_pairs": ["USDJPY"],
            "current_positions": [],
            "next_action": None,
            "error": None,
        }

        result = await economic_calendar_node(initial_state)

        # Should have economic context
        assert "economic_context" in result
        assert result["economic_context"] is not None


@pytest.mark.asyncio
async def test_orchestrator_routes_to_economic_first(mock_settings):
    """Test orchestrator routes to economic calendar when no context."""
    with patch("economic_calendar_agent.agent.orchestrator.ChatOpenAI") as mock_llm:
        # Mock LLM response
        llm_instance = mock_llm.return_value
        mock_response = MagicMock()
        mock_response.content = "Let's start by gathering economic calendar data."
        llm_instance.ainvoke = AsyncMock(return_value=mock_response)

        from economic_calendar_agent.agent.orchestrator import orchestrator_node

        initial_state: FXTradingState = {
            "messages": [],
            "economic_context": None,
            "technical_signals": None,
            "sentiment_scores": None,
            "risk_assessment": None,
            "target_pairs": ["USDJPY"],
            "current_positions": [],
            "next_action": None,
            "error": None,
        }

        result = await orchestrator_node(initial_state)

        # Should route to economic_calendar
        assert result["next_action"] == "economic_calendar"


@pytest.mark.asyncio
async def test_stub_nodes_return_data():
    """Test that stub nodes return expected data structures."""
    from economic_calendar_agent.agent.nodes.risk import risk_check_node
    from economic_calendar_agent.agent.nodes.sentiment import (
        sentiment_analysis_node,
    )
    from economic_calendar_agent.agent.nodes.technical import (
        technical_analysis_node,
    )

    initial_state: FXTradingState = {
        "messages": [],
        "economic_context": None,
        "technical_signals": None,
        "sentiment_scores": None,
        "risk_assessment": None,
        "target_pairs": ["USDJPY"],
        "current_positions": [],
        "next_action": None,
        "error": None,
    }

    # Test technical node
    tech_result = await technical_analysis_node(initial_state)
    assert "technical_signals" in tech_result
    assert tech_result["technical_signals"]["symbol"] is not None

    # Test sentiment node
    sent_result = await sentiment_analysis_node(initial_state)
    assert "sentiment_scores" in sent_result
    assert sent_result["sentiment_scores"]["overall"] is not None

    # Test risk node
    risk_result = await risk_check_node(initial_state)
    assert "risk_assessment" in risk_result
    assert risk_result["risk_assessment"]["risk_level"] is not None


@pytest.mark.asyncio
async def test_parse_next_action():
    """Test next action parsing from LLM responses."""
    from economic_calendar_agent.agent.orchestrator import _parse_next_action

    assert _parse_next_action("Let's check the economic calendar") == "economic_calendar"
    assert _parse_next_action("I need technical analysis") == "technical_analysis"
    assert _parse_next_action("Check sentiment scores") == "sentiment_analysis"
    assert _parse_next_action("Perform risk assessment") == "risk_check"
    assert _parse_next_action("Execute the trade") == "execute"
    assert _parse_next_action("We're done, analysis complete") == "END"
