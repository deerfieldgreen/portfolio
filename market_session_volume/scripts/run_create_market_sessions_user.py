#!/usr/bin/env python3
"""Run CREATE USER for market_sessions in ClickHouse. Uses admin creds from Doppler."""
import os
import sys

import clickhouse_connect

def main():
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    secure = os.getenv("CLICKHOUSE_SECURE", "").lower() in ("1", "true", "yes")
    admin_user = os.getenv("CLICKHOUSE_ADMIN_USERNAME")
    admin_pass = os.getenv("CLICKHOUSE_ADMIN_PASSWORD")
    market_sessions_pass = os.getenv("CLICKHOUSE_PASSWORD", "")

    if not admin_user or not admin_pass:
        print("CLICKHOUSE_ADMIN_USERNAME and CLICKHOUSE_ADMIN_PASSWORD required.", file=sys.stderr)
        print("(Admin creds connect to ClickHouse; CLICKHOUSE_PASSWORD is the market_sessions password to set)", file=sys.stderr)
        sys.exit(1)
    if not market_sessions_pass:
        print("CLICKHOUSE_PASSWORD (market_sessions) required. Run create_market_sessions_user.sh first.", file=sys.stderr)
        sys.exit(1)

    # Use admin for connection; market_sessions password is for the CREATE USER
    try:
        client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=admin_user,
            password=admin_pass,
            secure=secure,
        )
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Escape single quotes in password for SQL
    escaped = market_sessions_pass.replace("'", "''")

    stmts = [
        f"CREATE USER IF NOT EXISTS market_sessions IDENTIFIED BY '{escaped}'",
        f"ALTER USER market_sessions IDENTIFIED BY '{escaped}'",
        "GRANT SELECT, INSERT ON oanda_data_statistics.* TO market_sessions",
    ]

    for stmt in stmts:
        try:
            client.command(stmt)
            print("OK:", stmt[:60] + "..." if len(stmt) > 60 else stmt)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    print("Done. market_sessions user ready.")

if __name__ == "__main__":
    main()
