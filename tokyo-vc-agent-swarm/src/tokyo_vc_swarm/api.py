"""
FastAPI application for the Tokyo VC Deal Scoring Swarm.

Endpoints:
  POST /score          – Score and rank a batch of deal memos
  GET  /health         – Health check
  GET  /rankings       – Top-K deals from most recent ClickHouse ranking run
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import Config
from .pipeline import DealScoringPipeline
from .storage.clickhouse import ClickHouseWriter

logger = logging.getLogger(__name__)

_pipeline: Optional[DealScoringPipeline] = None
_ch_writer: Optional[ClickHouseWriter] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline, _ch_writer
    Config.validate()
    _pipeline = DealScoringPipeline()
    try:
        _ch_writer = ClickHouseWriter()
        _ch_writer.create_tables()
        logger.info("ClickHouse writer ready")
    except Exception as exc:
        logger.warning("ClickHouse unavailable at startup: %s", exc)
        _ch_writer = None
    yield


app = FastAPI(
    title="Tokyo VC Deal Scoring Swarm",
    description=(
        "LangGraph agent swarm that scores VC deal memos across 7 dimensions "
        "(Market, Team, Product/Moat, Traction, Syndication Fit, Risk/Regulatory, Japan Fit) "
        "and returns a composite-weighted ranked list."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ── Request / Response models ──────────────────────────────────────────────────

class ScoreRequest(BaseModel):
    deals: List[Dict[str, Any]] = Field(
        ...,
        description="List of deal JSON objects. Each should include a 'deal_id' key.",
        min_length=1,
    )
    weight_overrides: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            "Optional per-dimension weight overrides. "
            "Keys: market, team, product, traction, syndication_fit, risk_regulatory, japan_fit."
        ),
    )
    mock: bool = Field(
        default=False,
        description="If true, skip LLM calls and return stub scores (for testing).",
    )
    persist: bool = Field(
        default=True,
        description="If true, write results to ClickHouse (ignored if ClickHouse is unavailable).",
    )


class DimensionScoreOut(BaseModel):
    score: float
    weight: float
    rationale: str


class RankedDealOut(BaseModel):
    rank: int
    deal_id: str
    composite_score: float
    dimensions: Dict[str, DimensionScoreOut]
    explanation: str


class ScoreResponse(BaseModel):
    run_id: str
    ranked_deals: List[RankedDealOut]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/score", response_model=ScoreResponse)
def score_deals(request: ScoreRequest) -> ScoreResponse:
    """Score and rank a batch of deal memos."""
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialised")

    run_id = str(uuid.uuid4())
    try:
        ranked = _pipeline.run(
            deals=request.deals,
            weight_overrides=request.weight_overrides,
            mock=request.mock,
        )
    except Exception as exc:
        logger.error("Scoring failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Persist to ClickHouse if requested and available
    if request.persist and _ch_writer is not None:
        try:
            _ch_writer.write_scores(ranked, run_id)
            _ch_writer.write_rankings(ranked, run_id)
        except Exception as exc:
            logger.warning("ClickHouse write failed (non-fatal): %s", exc)

    return ScoreResponse(
        run_id=run_id,
        ranked_deals=[RankedDealOut(**d) for d in ranked],
    )


@app.get("/rankings", response_model=List[Dict[str, Any]])
def get_rankings(top_k: int = 10) -> List[Dict[str, Any]]:
    """Return top-K deals from the most recent ClickHouse ranking run."""
    if _ch_writer is None:
        raise HTTPException(status_code=503, detail="ClickHouse not available")
    try:
        return _ch_writer.get_top_k(k=top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
