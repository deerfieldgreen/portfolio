"""
Base scoring agent for all dimension agents.

Provides shared LLM call logic, <think> tag stripping, and JSON parsing
with graceful fallback so a single agent failure never blocks the swarm.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from openai import AsyncOpenAI

from ..config import Config
from ..state import DimensionScore

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


class BaseScoringAgent(ABC):
    """
    Abstract base for all dimension-scoring agents.

    Subclasses must implement:
      - DIMENSION_NAME: str class attribute
      - _build_prompt(deal_data: dict) -> str
    """

    DIMENSION_NAME: str = ""

    def __init__(self, weight: float = 1.0) -> None:
        novita = Config.get_novita_config()
        self._client = AsyncOpenAI(
            api_key=novita["api_key"],
            base_url=novita["base_url"],
        )
        self._model = novita["model"]
        self._temperature = novita["temperature"]
        self._max_tokens = novita["max_tokens"]
        self.weight = weight

    @abstractmethod
    def _build_prompt(self, deal_data: Dict[str, Any]) -> str:
        """Return the dimension-specific scoring prompt."""

    async def score_deal(self, deal_data: Dict[str, Any]) -> DimensionScore:
        """
        Score a single deal on this agent's dimension.

        Returns a DimensionScore with score=0 and a descriptive rationale on error,
        so the swarm continues even if one LLM call fails.
        """
        prompt = self._build_prompt(deal_data)
        try:
            raw = await self._call_llm(prompt)
            score, rationale = self._parse_response(raw)
            return DimensionScore(score=score, weight=self.weight, rationale=rationale)
        except Exception as exc:
            logger.warning(
                "Agent %s failed for deal %s: %s",
                self.DIMENSION_NAME,
                deal_data.get("deal_id", "unknown"),
                exc,
            )
            return DimensionScore(
                score=0.0,
                weight=self.weight,
                rationale=f"Scoring unavailable: {exc}",
            )

    async def _call_llm(self, prompt: str) -> str:
        """Call Novita AI and return the raw text response."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior VC analyst specialising in Tokyo and Japan "
                        "early-stage investments. Always respond with valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return response.choices[0].message.content or ""

    def _parse_response(self, raw: str) -> Tuple[float, str]:
        """
        Extract score and rationale from raw LLM output.

        Strips <think> tags, tries ```json``` fences, then falls back to
        the first {...} block in the response.
        """
        cleaned = _THINK_RE.sub("", raw).strip()

        # Try fenced code block first
        fence_match = _JSON_FENCE_RE.search(cleaned)
        if fence_match:
            candidate = fence_match.group(1).strip()
        else:
            # Fallback: find first {...} block
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            candidate = cleaned[start:end] if start >= 0 and end > start else ""

        parsed: Optional[Dict] = None
        if candidate:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                pass

        if parsed and "score" in parsed:
            score = float(max(0.0, min(10.0, parsed["score"])))
            rationale = str(parsed.get("rationale", "")).strip()
            return score, rationale

        raise ValueError(f"Could not parse JSON from LLM response: {cleaned[:200]}")
