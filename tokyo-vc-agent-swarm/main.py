"""
Tokyo VC Deal Scoring Swarm – CLI entry point.

Usage:
    python main.py --input deals.json                  # score from file
    cat deals.json | python main.py                    # score from stdin
    python main.py --input deals.json --top-k 5        # show top 5
    python main.py --input deals.json --mock            # stub scores (no LLM)
    python main.py --input deals.json --no-clickhouse  # skip persistence
"""

import argparse
import json
import logging
import sys
import uuid
from typing import Any, Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def load_deals(path: str | None) -> List[Dict[str, Any]]:
    if path:
        with open(path) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)
    if isinstance(data, dict):
        data = [data]
    return data


def print_table(ranked_deals: list) -> None:
    print(f"\n{'Rank':<6} {'Deal ID':<36} {'Score':>7}  Explanation")
    print("-" * 100)
    for deal in ranked_deals:
        print(
            f"{deal['rank']:<6} {deal['deal_id']:<36} {deal['composite_score']:>7.3f}  "
            f"{deal['explanation'][:70]}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Tokyo VC Deal Scoring Swarm")
    parser.add_argument("--input", "-i", help="Path to JSON file (default: stdin)")
    parser.add_argument("--top-k", "-k", type=int, default=10, help="Number of top deals to show")
    parser.add_argument("--mock", action="store_true", help="Skip LLM calls, use stub scores")
    parser.add_argument("--no-clickhouse", action="store_true", help="Skip ClickHouse persistence")
    args = parser.parse_args()

    deals = load_deals(args.input)
    logger.info("Loaded %d deal(s)", len(deals))

    from tokyo_vc_swarm.pipeline import DealScoringPipeline

    pipeline = DealScoringPipeline()
    run_id = str(uuid.uuid4())

    logger.info("Run ID: %s", run_id)

    for event in pipeline.stream(deals, mock=args.mock):
        if event["type"] == "status":
            logger.info("[%s]", event["message"])
        elif event["type"] == "error":
            logger.error("Pipeline error: %s", event["message"])
            sys.exit(1)
        elif event["type"] == "complete":
            ranked = event["ranked_output"]
            top = ranked[: args.top_k]
            print_table(top)

            if not args.no_clickhouse:
                try:
                    from tokyo_vc_swarm.storage.clickhouse import ClickHouseWriter
                    writer = ClickHouseWriter()
                    writer.create_tables()
                    writer.write_scores(ranked, run_id)
                    writer.write_rankings(ranked, run_id)
                    logger.info("Results persisted to ClickHouse (run_id=%s)", run_id)
                except Exception as exc:
                    logger.warning("ClickHouse write failed (non-fatal): %s", exc)


if __name__ == "__main__":
    main()
