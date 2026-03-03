"""Product / moat scoring agent."""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import BaseScoringAgent


class ProductAgent(BaseScoringAgent):
    """Scores product defensibility: IP, moat, and localization complexity."""

    DIMENSION_NAME = "product"

    def _build_prompt(self, deal_data: Dict[str, Any]) -> str:
        return (
            "You are a VC analyst scoring deals in Tokyo.\n"
            "Dimension: **Product / Moat** – evaluate the product's defensibility "
            "and competitive moat, especially in the Japan context.\n\n"
            "Consider: proprietary technology or IP, switching costs, network effects, "
            "localization complexity that creates a natural barrier for foreign entrants, "
            "and stage of product maturity.\n\n"
            "Score from 0 (commodity product) to 10 (strong moat) and explain briefly in 2 sentences.\n\n"
            "Output JSON only:\n"
            '{ "score": <0-10 number>, "rationale": "<text>" }\n\n'
            f"Deal data:\n```json\n{json.dumps(deal_data, ensure_ascii=False, indent=2)}\n```"
        )
