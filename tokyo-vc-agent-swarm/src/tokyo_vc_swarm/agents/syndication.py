"""Syndication fit scoring agent."""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import BaseScoringAgent


class SyndicationAgent(BaseScoringAgent):
    """Scores syndication fit: suitability for co-investment with other VCs/CVCs."""

    DIMENSION_NAME = "syndication_fit"

    def _build_prompt(self, deal_data: Dict[str, Any]) -> str:
        return (
            "You are a VC analyst scoring deals in Tokyo.\n"
            "Dimension: **Syndication Fit** – how suitable is this deal for small joint "
            "investments and co-investment with other VCs and CVCs.\n\n"
            "Consider: round size and whether it accommodates multiple investors, "
            "minimum check size, existing investor quality and complementarity, "
            "sector attractiveness for CVC strategic interest, "
            "and stage alignment with typical syndication partners.\n\n"
            "Score from 0 (not suitable for syndication) to 10 (ideal syndication deal) "
            "and explain briefly in 2 sentences.\n\n"
            "Output JSON only:\n"
            '{ "score": <0-10 number>, "rationale": "<text>" }\n\n'
            f"Deal data:\n```json\n{json.dumps(deal_data, ensure_ascii=False, indent=2)}\n```"
        )
