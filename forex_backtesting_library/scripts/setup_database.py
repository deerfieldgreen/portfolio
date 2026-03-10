#!/usr/bin/env python3
"""
setup_database.py: Create the vectorbt_grid database, dedicated user, and tables.
Run once against ClickHouse with admin credentials. Use the created user for app/CLI.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import clickhouse_connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def get_database() -> str:
    """Database name from CLICKHOUSE_DATABASE env."""
    return os.environ.get("CLICKHOUSE_DATABASE", "vectorbt_grid")


def get_username() -> str:
    """Username from CLICKHOUSE_USERNAME env (required, no fallback)."""
    return os.environ["CLICKHOUSE_USERNAME"]


def get_admin_client():
    """Connect to ClickHouse as admin (root or default). Use default DB so we can create vectorbt_grid."""
    host = os.environ.get("CLICKHOUSE_HOST", "localhost")
    port = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
    username = os.environ["CLICKHOUSE_USERNAME"].strip()
    password = (os.environ.get("CLICKHOUSE_PASSWORD", "") or "").strip()
    secure = os.environ.get("CLICKHOUSE_SECURE", "false").lower() == "true"
    if username == get_username():
        logger.error(
            "Run setup_database.py with admin credentials (root or default), not as %s. "
            "Example: export CLICKHOUSE_USERNAME=root CLICKHOUSE_PASSWORD=<admin-password>",
            get_username(),
        )
        sys.exit(1)
    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=username,
        password=password,
        database="default",
        secure=secure,
    )
    logger.info("Connected to ClickHouse as admin (database=default)")
    return client


def create_database(client: clickhouse_connect.driver.Client):
    """Create database from CLICKHOUSE_DATABASE if not exists."""
    database = get_database()
    client.command(f"CREATE DATABASE IF NOT EXISTS {database}")
    logger.info("Database %s ensured", database)


def create_user(client: clickhouse_connect.driver.Client, password: str):
    """Create dedicated user from CLICKHOUSE_USERNAME and grant full access to CLICKHOUSE_DATABASE.*."""
    database = get_database()
    username = get_username()
    password = password.strip()
    escaped = password.replace("'", "''")
    # Recreate user so password/format is correct (e.g. after fixing auth or env)
    client.command(f"DROP USER IF EXISTS {username}")
    client.command(
        f"CREATE USER {username} IDENTIFIED WITH sha256_password BY '{escaped}'"
    )
    logger.info("User %s created", username)
    client.command(f"GRANT ALL ON {database}.* TO {username}")
    client.command(f"GRANT CREATE TABLE ON {database}.* TO {username}")
    logger.info("Granted ALL and CREATE TABLE on %s.* to %s", database, username)


def create_tables(client: clickhouse_connect.driver.Client):
    """Create tables from create_tables.sql. Substitutes {DATABASE} with CLICKHOUSE_DATABASE."""
    script_dir = Path(__file__).parent
    sql_file = script_dir / "create_tables.sql"
    if not sql_file.exists():
        raise FileNotFoundError(f"Schema not found: {sql_file}")
    with open(sql_file) as f:
        sql = f.read()
    database = get_database()
    sql = sql.replace("{DATABASE}", database)
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement and not statement.startswith("--"):
            client.command(statement)
            logger.debug("Executed: %s", statement[:60] + "..." if len(statement) > 60 else statement)
    logger.info("Tables in %s created (backtests, backtest_trades, backtest_grid_results)", database)


def main():
    parser = argparse.ArgumentParser(
        description="Create vectorbt_grid database, user, and tables in ClickHouse."
    )
    parser.add_argument(
        "--user-password",
        default=os.environ.get("VECTORBT_GRID_USER_PASSWORD", ""),
        help="Password for the vectorbt_grid user (or set VECTORBT_GRID_USER_PASSWORD)",
    )
    args = parser.parse_args()
    args.user_password = (args.user_password or "").strip()

    if not args.user_password:
        logger.error(
            "Set the vectorbt_grid user password: --user-password PASSWORD or "
            "VECTORBT_GRID_USER_PASSWORD environment variable"
        )
        return 1

    try:
        client = get_admin_client()
        create_database(client)
        create_user(client, args.user_password)
        create_tables(client)
        logger.info("Setup complete. Use CLICKHOUSE_USERNAME=%s and CLICKHOUSE_PASSWORD=<same> for the app.", get_username())
        return 0
    except Exception as e:
        logger.error("Setup failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
