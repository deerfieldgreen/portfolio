"""Team quality scoring agent."""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import BaseScoringAgent


class TeamAgent(BaseScoringAgent):
    """Scores founding team quality: track record, exits, and technical depth."""

    DIMENSION_NAME = "team"

    def _build_prompt(self, deal_data: Dict[str, Any]) -> str:
        return (
            "You are a VC analyst scoring deals in Tokyo.\n"
            "Dimension: **Team Quality** – evaluate the founding team's strength for execution "
            "in the Tokyo/Japan market.\n\n"
            "Consider: founders' prior exits or notable experience, domain expertise, "
            "technical depth, Japan market knowledge, and team completeness (CEO/CTO/bizdev).\n\n"
            "Score from 0 (weak team) to 10 (exceptional team) and explain briefly in 2 sentences.\n\n"
            "Output JSON only:\n"
            '{ "score": <0-10 number>, "rationale": "<text>" }\n\n'
            f"Deal data:\n```json\n{json.dumps(deal_data, ensure_ascii=False, indent=2)}\n```"
        )
