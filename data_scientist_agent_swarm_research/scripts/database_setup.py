"""
Apply ClickHouse schema for fxs_* tables in cervid_analytics.
Usage: python -m scripts.database_setup
"""
import sys
from pathlib import Path

from src.shared.ch_client import get_client


def main():
    sql_path = Path(__file__).parent.parent / "k8s" / "clickhouse-tables.sql"
    if not sql_path.exists():
        print(f"FATAL: SQL file not found at {sql_path}")
        sys.exit(1)

    sql_content = sql_path.read_text()

    # Split on semicolons, filter empty statements
    statements = [s.strip() for s in sql_content.split(";") if s.strip()]

    client = get_client()

    errors = 0
    for i, stmt in enumerate(statements, 1):
        # Skip comments-only blocks
        lines = [l for l in stmt.split("\n") if l.strip() and not l.strip().startswith("--")]
        if not lines:
            continue

        try:
            client.command(stmt)
            print(f"[{i}/{len(statements)}] OK")
        except Exception as e:
            print(f"[{i}/{len(statements)}] ERROR: {e}")
            print(f"  Statement: {stmt[:100]}...")
            errors += 1

    if errors:
        print(f"Schema setup completed with {errors} error(s).")
        sys.exit(1)

    print("Schema setup complete — all statements OK.")


if __name__ == "__main__":
    main()
