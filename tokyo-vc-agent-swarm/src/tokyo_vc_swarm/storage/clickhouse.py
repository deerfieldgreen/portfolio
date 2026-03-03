"""
ClickHouse storage layer for deal scores and rankings.

Tables:
  - deal_scores: one row per (deal_id, scored_at) with all dimension scores as JSON
  - deal_rankings: one row per (run_id, rank) for quick top-K queries
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import clickhouse_connect

from ..config import Config
from ..state import RankedDeal

logger = logging.getLogger(__name__)

_CREATE_SCORES_TABLE = """
CREATE TABLE IF NOT EXISTS {database}.{scores_table}
(
    deal_id        String,
    run_id         String,
    scored_at      DateTime,
    composite_score Float64,
    rank           UInt32,
    dimensions_json String,
    explanation    String
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(scored_at)
ORDER BY (deal_id, scored_at)
"""

_CREATE_RANKINGS_TABLE = """
CREATE TABLE IF NOT EXISTS {database}.{rankings_table}
(
    run_id         String,
    ranked_at      DateTime,
    rank           UInt32,
    deal_id        String,
    composite_score Float64,
    explanation    String
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(ranked_at)
ORDER BY (run_id, rank)
"""


class ClickHouseWriter:
    """Writes scoring results and rankings to ClickHouse."""

    def __init__(self) -> None:
        cfg = Config.get_clickhouse_config()
        self._client = clickhouse_connect.get_client(
            host=cfg["host"],
            port=cfg["port"],
            username=cfg["username"],
            password=cfg["password"],
            database=cfg["database"],
        )
        self._scores_table = cfg["scores_table"]
        self._rankings_table = cfg["rankings_table"]
        self._database = cfg["database"]

    def create_tables(self) -> None:
        """Create deal_scores and deal_rankings tables if they don't exist."""
        for ddl in [_CREATE_SCORES_TABLE, _CREATE_RANKINGS_TABLE]:
            self._client.command(
                ddl.format(
                    database=self._database,
                    scores_table=self._scores_table,
                    rankings_table=self._rankings_table,
                )
            )
        logger.info("ClickHouse tables ensured: %s, %s", self._scores_table, self._rankings_table)

    def write_scores(self, ranked_deals: List[RankedDeal], run_id: str) -> None:
        """Write per-deal dimension scores to deal_scores table."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows = []
        for deal in ranked_deals:
            rows.append([
                deal["deal_id"],
                run_id,
                now,
                float(deal["composite_score"]),
                int(deal["rank"]),
                json.dumps(deal["dimensions"], ensure_ascii=False),
                deal["explanation"],
            ])
        if rows:
            self._client.insert(
                f"{self._database}.{self._scores_table}",
                rows,
                column_names=["deal_id", "run_id", "scored_at", "composite_score",
                               "rank", "dimensions_json", "explanation"],
            )
            logger.info("Wrote %d rows to %s", len(rows), self._scores_table)

    def write_rankings(self, ranked_deals: List[RankedDeal], run_id: str) -> None:
        """Write ranking snapshot to deal_rankings table."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows = []
        for deal in ranked_deals:
            rows.append([
                run_id,
                now,
                int(deal["rank"]),
                deal["deal_id"],
                float(deal["composite_score"]),
                deal["explanation"],
            ])
        if rows:
            self._client.insert(
                f"{self._database}.{self._rankings_table}",
                rows,
                column_names=["run_id", "ranked_at", "rank", "deal_id",
                               "composite_score", "explanation"],
            )
            logger.info("Wrote %d rows to %s", len(rows), self._rankings_table)

    def get_top_k(self, k: int = 10) -> List[Dict[str, Any]]:
        """Return top-K deals from the most recent ranking run."""
        result = self._client.query(
            f"""
            SELECT run_id, rank, deal_id, composite_score, explanation
            FROM {self._database}.{self._rankings_table}
            WHERE run_id = (
                SELECT run_id FROM {self._database}.{self._rankings_table}
                ORDER BY ranked_at DESC LIMIT 1
            )
            ORDER BY rank ASC
            LIMIT %(k)s
            """,
            parameters={"k": k},
        )
        return [dict(zip(result.column_names, row)) for row in result.result_rows]
