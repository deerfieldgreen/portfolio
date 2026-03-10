"""Risk assessment tool node (stub for Phase 2)."""
from __future__ import annotations

import logging

from ..state import FXTradingState, RiskAssessment

logger = logging.getLogger(__name__)


async def risk_check_node(state: FXTradingState) -> dict:
    """Perform risk assessment (stub).

    Args:
        state: Current agent state

    Returns:
        Dict with risk_assessment field populated
    """
    logger.info("Risk check node (stub)")

    # Stub implementation — return conservative risk assessment
    risk_assessment = RiskAssessment(
        risk_level="medium",
        position_size=0.01,  # 1% of capital
        stop_loss=None,
        take_profit=None,
    )

    return {"risk_assessment": risk_assessment}
