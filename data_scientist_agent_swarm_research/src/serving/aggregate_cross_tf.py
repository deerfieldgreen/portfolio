"""
Aggregate cross-timeframe snapshot.
Runs after all pair/TF pods complete.
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"

from datetime import datetime
from src.shared.ch_client import get_client


def main():
    ch = get_client()

    # Get all active pairs
    pairs = ch.query(
        "SELECT DISTINCT pair FROM fxs_serving_universe WHERE active = 1"
    ).result_rows

    for (pair,) in pairs:
        # Get latest predictions per timeframe
        rows = ch.query(
            "SELECT timeframe, pred_next_close, actual_close, error_pips "
            "FROM fxs_predictions "
            "WHERE pair = %(pair)s "
            "ORDER BY timestamp DESC "
            "LIMIT 1 BY timeframe",
            parameters={"pair": pair},
        ).named_results()

        if not rows:
            continue

        data = {}
        for row in rows:
            tf = row["timeframe"].lower()
            data[f"{tf}_pred"] = float(row["pred_next_close"])
            if row["actual_close"] is not None:
                data[f"{tf}_actual"] = float(row["actual_close"])
            if row["error_pips"] is not None:
                data[f"{tf}_error_pips"] = float(row["error_pips"])

        # Determine trend alignment (all TFs agree on direction)
        preds = [v for k, v in data.items() if k.endswith("_pred")]
        actuals = [v for k, v in data.items() if k.endswith("_actual")]
        trend_aligned = 0
        if len(preds) >= 2 and len(actuals) >= 2:
            directions = [1 if p > a else -1 for p, a in zip(preds, actuals)]
            trend_aligned = 1 if len(set(directions)) == 1 else 0

        ch.insert(
            "fxs_cross_tf_snapshot",
            data=[[pair, datetime.utcnow(), data, trend_aligned]],
            column_names=["pair", "snapshot_ts", "data", "trend_aligned"],
        )

    print("Cross-TF aggregation complete")


if __name__ == "__main__":
    main()
