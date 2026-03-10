"""ExpeL-style insight storage and retrieval."""
import uuid
from datetime import datetime
from src.shared.ch_client import get_client


def store_insight(
    text: str,
    source_run_ids: list,
    category: str,
    confidence: float = 0.5,
) -> str:
    """Store a new insight extracted by the meta-learner."""
    ch = get_client()
    insight_id = str(uuid.uuid4())
    now = datetime.utcnow()

    ch.insert(
        "fxs_insights",
        data=[[insight_id, text, source_run_ids, now, now,
               "active", confidence, category]],
        column_names=["insight_id", "text", "source_run_ids",
                     "created_at", "updated_at", "status",
                     "confidence", "category"],
    )
    return insight_id


def get_active_insights(limit: int = 50) -> list:
    """Get active insights ordered by confidence."""
    ch = get_client()
    result = ch.query(
        "SELECT insight_id, text, confidence, category "
        "FROM fxs_insights "
        "WHERE status = 'active' "
        "ORDER BY confidence DESC "
        "LIMIT %(limit)s",
        parameters={"limit": limit},
    )
    return [dict(r) for r in result.named_results()]


def update_insight_confidence(insight_id: str, new_confidence: float):
    """Update confidence based on new evidence."""
    ch = get_client()
    ch.command(
        f"ALTER TABLE fxs_insights UPDATE "
        f"confidence = {new_confidence}, updated_at = now64(3) "
        f"WHERE insight_id = '{insight_id}'"
    )


def deactivate_insight(insight_id: str):
    """Mark insight as inactive."""
    ch = get_client()
    ch.command(
        f"ALTER TABLE fxs_insights UPDATE "
        f"status = 'inactive', updated_at = now64(3) "
        f"WHERE insight_id = '{insight_id}'"
    )
