"""Market attractiveness scoring agent."""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import BaseScoringAgent


class MarketAgent(BaseScoringAgent):
    """Scores market attractiveness: TAM, competition, and Japan/Tokyo fit."""

    DIMENSION_NAME = "market"

    def _build_prompt(self, deal_data: Dict[str, Any]) -> str:
        return (
            "You are a VC analyst scoring deals in Tokyo.\n"
            "Dimension: **Market Attractiveness** – evaluate the total addressable market (TAM), "
            "competitive dynamics, and how well the market opportunity fits Japan/Tokyo.\n\n"
            "Consider: market size and growth rate, competitive density, barriers to entry, "
            "and any Japan-specific tailwinds or headwinds.\n\n"
            "Score from 0 (unattractive) to 10 (exceptional) and explain briefly in 2 sentences.\n\n"
            "Output JSON only:\n"
            '{ "score": <0-10 number>, "rationale": "<text>" }\n\n'
            f"Deal data:\n```json\n{json.dumps(deal_data, ensure_ascii=False, indent=2)}\n```"
        )
