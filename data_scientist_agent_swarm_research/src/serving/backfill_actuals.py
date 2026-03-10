"""Backfill actual close prices into predictions table."""
import logging
from src.shared.ch_client import get_client
from src.shared.config import SharedConfig

log = logging.getLogger(__name__)
cfg = SharedConfig()


def backfill(pair: str, timeframe: str):
    """
    For predictions that have NULL actual_close, fill in from instrument_features.
    Also compute error_pips.
    """
    ch = get_client()
    pip = cfg.pip_size(pair)

    # Check if there are any predictions to backfill
    count = ch.query(
        "SELECT count() FROM fxs_predictions "
        "WHERE pair = {pair:String} AND timeframe = {tf:String} AND actual_close IS NULL",
        parameters={"pair": pair, "tf": timeframe},
    ).result_rows[0][0]

    if count == 0:
        log.info("No predictions to backfill for %s/%s", pair, timeframe)
        return

    # Use parameterized literals instead of correlated subqueries
    ch.command(f"""
        ALTER TABLE fxs_predictions
        UPDATE
            actual_close = (
                SELECT close FROM fxs_instrument_features
                WHERE pair = '{pair}'
                AND timeframe = '{timeframe}'
                AND timestamp = fxs_predictions.timestamp
                LIMIT 1
            ),
            error_pips = abs(pred_next_close - (
                SELECT close FROM fxs_instrument_features
                WHERE pair = '{pair}'
                AND timeframe = '{timeframe}'
                AND timestamp = fxs_predictions.timestamp
                LIMIT 1
            )) / {pip}
        WHERE pair = '{pair}'
        AND timeframe = '{timeframe}'
        AND actual_close IS NULL
        AND timestamp IN (
            SELECT timestamp FROM fxs_instrument_features
            WHERE pair = '{pair}' AND timeframe = '{timeframe}'
        )
    """)
