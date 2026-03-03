"""Traction / financials scoring agent."""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import BaseScoringAgent


class TractionAgent(BaseScoringAgent):
    """Scores traction and financial health: ARR/MRR, growth, and retention."""

    DIMENSION_NAME = "traction"

    def _build_prompt(self, deal_data: Dict[str, Any]) -> str:
        return (
            "You are a VC analyst scoring deals in Tokyo.\n"
            "Dimension: **Traction / Financials** – evaluate the company's demonstrated "
            "traction and financial trajectory.\n\n"
            "Consider: current ARR or MRR, month-over-month or year-over-year growth rate, "
            "customer retention and churn, unit economics (CAC/LTV), and burn rate relative to runway.\n\n"
            "Score from 0 (no traction) to 10 (exceptional traction) and explain briefly in 2 sentences.\n\n"
            "Output JSON only:\n"
            '{ "score": <0-10 number>, "rationale": "<text>" }\n\n'
            f"Deal data:\n```json\n{json.dumps(deal_data, ensure_ascii=False, indent=2)}\n```"
        )
