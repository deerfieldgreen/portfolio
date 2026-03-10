"""
Data quality validation. Runs after aggregation.
Checks for stale data, missing predictions, anomalies.
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import sys
from src.shared.ch_client import get_client
from src.shared.discord import notify_discord


def main():
    ch = get_client()
    issues = []

    # Check 1: All active pairs have recent features (within 2 hours)
    stale = ch.query("""
        SELECT su.pair, su.timeframe,
               max(f.inserted_at) as last_insert
        FROM fxs_serving_universe su
        LEFT JOIN fxs_instrument_features f
            ON su.pair = f.pair AND su.timeframe = f.timeframe
        WHERE su.active = 1
        GROUP BY su.pair, su.timeframe
        HAVING last_insert < now() - INTERVAL 2 HOUR
            OR last_insert IS NULL
    """).named_results()

    for row in stale:
        issues.append(f"Stale features: {row['pair']}/{row['timeframe']}")

    # Check 2: No NaN/Inf in recent features
    bad_features = ch.query("""
        SELECT pair, timeframe, count() as cnt
        FROM fxs_instrument_features
        WHERE inserted_at > now() - INTERVAL 1 HOUR
        AND (isNaN(close) OR isInfinite(close) OR close = 0)
        GROUP BY pair, timeframe
    """).named_results()

    for row in bad_features:
        issues.append(f"Bad features ({row['cnt']}): {row['pair']}/{row['timeframe']}")

    if issues:
        msg = "FX Serving Validation Issues:\n" + "\n".join(f"- {i}" for i in issues)
        print(msg)
        notify_discord(msg)
        sys.exit(1)
    else:
        print("Validation passed: all checks OK")


if __name__ == "__main__":
    main()
