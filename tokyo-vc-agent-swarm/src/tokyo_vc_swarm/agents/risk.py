"""Risk / regulatory scoring agent."""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import BaseScoringAgent


class RiskAgent(BaseScoringAgent):
    """
    Scores regulatory and operational risk.

    Note: this score is **inverted** by the composite ranker (higher risk → lower composite),
    as configured by `invert: true` in config.yaml.
    """

    DIMENSION_NAME = "risk_regulatory"

    def _build_prompt(self, deal_data: Dict[str, Any]) -> str:
        return (
            "You are a VC analyst scoring deals in Tokyo.\n"
            "Dimension: **Risk / Regulatory** – evaluate the overall risk level of this deal, "
            "with emphasis on Japan-specific regulatory exposure.\n\n"
            "Consider: FEFTA (Foreign Exchange and Foreign Trade Act) restrictions, "
            "sector-specific licensing requirements (fintech, healthcare, crypto), "
            "FX/currency risk if revenue is multi-currency, "
            "litigation or IP dispute history, and key-person concentration risk.\n\n"
            "Score from 0 (extremely high risk) to 10 (very low risk) "
            "and explain briefly in 2 sentences.\n\n"
            "Output JSON only:\n"
            '{ "score": <0-10 number>, "rationale": "<text>" }\n\n'
            f"Deal data:\n```json\n{json.dumps(deal_data, ensure_ascii=False, indent=2)}\n```"
        )
