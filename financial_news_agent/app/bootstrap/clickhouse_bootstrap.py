#!/usr/bin/env python3
"""
Bootstrap ClickHouse schema for the financial news agent pipeline.
Creates tables, materialized views, and query views — idempotent (IF NOT EXISTS).

Executes SQL files in order from bootstrap/sql/, replacing ${CLICKHOUSE_DATABASE}
with the value of the CLICKHOUSE_DATABASE env var (required, no fallback).

Pattern follows market_regime_detection/data_processing/setup_tables.py.
"""

import os
import sys
import logging
from pathlib import Path

import clickhouse_connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_client():
    host = os.environ["CLICKHOUSE_HOST"]
    port = int(os.environ.get("CLICKHOUSE_PORT", 8123))
    username = os.environ["CLICKHOUSE_USERNAME"]
    password = os.environ.get("CLICKHOUSE_PASSWORD", "")
    secure = os.environ.get("CLICKHOUSE_SECURE", "").lower() in ("true", "1", "yes")

    return clickhouse_connect.get_client(
        host=host, port=port, username=username, password=password, secure=secure
    )


def execute_sql_file(client, sql_file: Path, database: str, optional: bool = False):
    logger.info(f"Executing {sql_file.name}")
    raw = sql_file.read_text().replace("${CLICKHOUSE_DATABASE}", database)
    # Strip single-line comments before splitting by ';' so semicolons
    # inside comments (e.g. "-- id from uuid5(url); scores JSON") are harmless.
    lines = [l for l in raw.splitlines() if not l.strip().startswith("--")]
    sql = "\n".join(lines)
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    for i, stmt in enumerate(statements):
        try:
            client.command(stmt)
            logger.info(f"  [{sql_file.name}] statement {i+1}/{len(statements)} OK")
        except Exception as e:
            if optional:
                logger.warning(f"  [{sql_file.name}] statement {i+1} skipped (optional): {e}")
            else:
                logger.error(f"  [{sql_file.name}] statement {i+1} failed: {e}")
                raise


def main():
    database = os.environ["CLICKHOUSE_DATABASE"]
    logger.info(f"Bootstrapping ClickHouse schema in database: {database}")

    client = get_client()
    logger.info("Connected to ClickHouse")

    sql_dir = Path(__file__).parent / "sql"
    execute_sql_file(client, sql_dir / "01_create_tables.sql", database)
    execute_sql_file(client, sql_dir / "02_mv_hourly_scores.sql", database, optional=True)
    execute_sql_file(client, sql_dir / "03_mv_minute_scores.sql", database, optional=True)

    logger.info("Bootstrap complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
