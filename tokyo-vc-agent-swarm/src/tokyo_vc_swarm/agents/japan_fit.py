"""Strategic Japan / Tokyo fit scoring agent."""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import BaseScoringAgent


class JapanFitAgent(BaseScoringAgent):
    """Scores strategic alignment with the Japan/Tokyo market and ecosystem."""

    DIMENSION_NAME = "japan_fit"

    def _build_prompt(self, deal_data: Dict[str, Any]) -> str:
        return (
            "You are a VC analyst scoring deals in Tokyo.\n"
            "Dimension: **Japan / Tokyo Strategic Fit** – evaluate how well this company "
            "is positioned to succeed specifically in the Japan and Tokyo market.\n\n"
            "Consider: localisation readiness (language, UX, business culture), "
            "existing Japan customer base or partnerships, government or keiretsu alignment, "
            "product-market fit for Japanese enterprise or consumer behaviour, "
            "and founder familiarity with the Japan ecosystem.\n\n"
            "Score from 0 (no Japan fit) to 10 (exceptional Japan fit) "
            "and explain briefly in 2 sentences.\n\n"
            "Output JSON only:\n"
            '{ "score": <0-10 number>, "rationale": "<text>" }\n\n'
            f"Deal data:\n```json\n{json.dumps(deal_data, ensure_ascii=False, indent=2)}\n```"
        )
