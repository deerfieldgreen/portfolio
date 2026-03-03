"""Unit tests for BaseScoringAgent JSON parsing and error handling."""

from __future__ import annotations

import pytest

from tokyo_vc_swarm.agents.base import BaseScoringAgent


class ConcreteAgent(BaseScoringAgent):
    DIMENSION_NAME = "test"

    def __init__(self):
        # Skip real __init__ (needs API key) – override directly
        self.weight = 1.0

    def _build_prompt(self, deal_data):
        return "test prompt"


@pytest.fixture
def agent():
    return ConcreteAgent()


def test_parse_fenced_json(agent):
    raw = '```json\n{"score": 8.5, "rationale": "Strong market"}\n```'
    score, rationale = agent._parse_response(raw)
    assert score == 8.5
    assert rationale == "Strong market"


def test_parse_bare_json(agent):
    raw = '{"score": 6, "rationale": "Moderate fit"}'
    score, rationale = agent._parse_response(raw)
    assert score == 6.0
    assert "Moderate" in rationale


def test_parse_strips_think_tags(agent):
    raw = "<think>Some reasoning here...</think>\n```json\n{\"score\": 9, \"rationale\": \"Excellent\"}\n```"
    score, rationale = agent._parse_response(raw)
    assert score == 9.0
    assert rationale == "Excellent"


def test_score_clamped_to_10(agent):
    raw = '{"score": 15, "rationale": "Off the charts"}'
    score, _ = agent._parse_response(raw)
    assert score == 10.0


def test_score_clamped_to_0(agent):
    raw = '{"score": -3, "rationale": "Terrible"}'
    score, _ = agent._parse_response(raw)
    assert score == 0.0


def test_parse_invalid_raises(agent):
    with pytest.raises(ValueError):
        agent._parse_response("not json at all")
