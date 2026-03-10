#!/usr/bin/env python3
"""
Create ClickHouse tables and views for market regime detection.
Executes SQL files in order. Assumes the database already exists (created by admin).
"""

import os
import sys
import logging
from pathlib import Path

import clickhouse_connect

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
    sql = sql_file.read_text().replace("${CLICKHOUSE_DATABASE}", database)
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    for i, stmt in enumerate(statements):
        lines = [l for l in stmt.splitlines() if l.strip() and not l.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if not stmt:
            continue
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
    logger.info(f"Setting up tables in {database}")

    client = get_client()
    logger.info("Connected to ClickHouse")

    sql_dir = Path(__file__).parent / "sql"
    execute_sql_file(client, sql_dir / "02_create_regime_states_table.sql", database)
    execute_sql_file(client, sql_dir / "03_create_transition_matrices_table.sql", database)
    execute_sql_file(client, sql_dir / "04_create_materialized_views.sql", database, optional=True)
    execute_sql_file(client, sql_dir / "05_add_fred_macro_columns.sql", database, optional=True)
    execute_sql_file(client, sql_dir / "06_add_enriched_columns.sql", database, optional=True)
    execute_sql_file(client, sql_dir / "07_rename_macro_columns.sql", database, optional=True)
    execute_sql_file(client, sql_dir / "08_add_garch_column.sql", database, optional=True)
    execute_sql_file(client, sql_dir / "09_add_transition_metrics.sql", database, optional=True)
    execute_sql_file(client, sql_dir / "10_migrate_replacing_merge_tree.sql", database, optional=True)
    execute_sql_file(client, sql_dir / "11_add_pca_metadata_columns.sql", database, optional=True)

    logger.info("Table setup complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
