"""
Single entry point per pod. Sequential: ingest → features → inference → write.
Usage: python -m src.serving.process_pair_tf
Env vars: PAIR, TIMEFRAME, OANDA_INSTRUMENT, CANDLE_COUNT
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from src.serving.ingest_ohlcv import ingest
from src.serving.compute_features import compute
from src.serving.serve_model import predict
from src.serving.write_clickhouse import write_features, write_predictions
from src.serving.backfill_actuals import backfill


def main():
    pair = os.environ["PAIR"]
    timeframe = os.environ["TIMEFRAME"]
    instrument = os.environ["OANDA_INSTRUMENT"]
    count = int(os.environ.get("CANDLE_COUNT", "500"))

    print(f"Processing {pair}/{timeframe} ({instrument}, {count} candles)")

    # 1. Ingest OHLCV from oanda-caching-api
    candles = ingest(instrument, timeframe, count)
    print(f"  Ingested {len(candles)} candles")

    # 2. Compute features
    features_df = compute(candles, pair, timeframe)
    print(f"  Computed {len(features_df.columns)} features")

    # 3. Write features to ClickHouse
    write_features(features_df, pair, timeframe)

    # 4. Run inference (if champion model exists)
    predictions = predict(features_df, pair, timeframe)
    if predictions is not None:
        write_predictions(predictions, pair, timeframe)
        print(f"  Wrote {len(predictions)} predictions")
    else:
        print(f"  No champion model for fx-{pair}-{timeframe}, skipping inference")

    # 5. Backfill actuals for past predictions
    backfill(pair, timeframe)

    print(f"Done: {pair}/{timeframe}")


if __name__ == "__main__":
    main()
