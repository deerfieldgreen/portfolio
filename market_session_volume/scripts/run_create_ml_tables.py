#!/usr/bin/env python3
"""Run create_ml_tables.sql against ClickHouse. Uses env vars for credentials."""
import os
import sys

import clickhouse_connect

def main():
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    database = os.getenv("CLICKHOUSE_DATABASE", "oanda_data_statistics")
    # Use admin credentials for setup (app user doesn't exist yet)
    username = os.environ.get("CLICKHOUSE_ADMIN_USERNAME") or os.environ["CLICKHOUSE_USERNAME"]
    password = os.getenv("CLICKHOUSE_ADMIN_PASSWORD") or os.getenv("CLICKHOUSE_PASSWORD", "")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    sql_path = os.path.join(script_dir, "create_ml_tables.sql")

    try:
        client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=username,
            password=password,
            secure=os.getenv("CLICKHOUSE_SECURE", "").lower() in ("1", "true", "yes"),
        )
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print("Set CLICKHOUSE_HOST, CLICKHOUSE_DATABASE, CLICKHOUSE_ADMIN_USERNAME, CLICKHOUSE_ADMIN_PASSWORD", file=sys.stderr)
        print("(Admin creds required - app user is created by create_market_sessions_user.sh)", file=sys.stderr)
        sys.exit(1)

    with open(sql_path) as f:
        content = f.read()

    content = content.replace("${CLICKHOUSE_DATABASE}", database)

    for stmt in content.split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("--"):
            try:
                client.command(stmt)
                print("OK:", stmt[:70] + "..." if len(stmt) > 70 else stmt)
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

    print("Done!")

if __name__ == "__main__":
    main()
