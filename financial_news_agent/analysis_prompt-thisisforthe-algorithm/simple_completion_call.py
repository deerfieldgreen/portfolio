#!/usr/bin/env python3
"""
Standalone CLI: fetch hourly-trend-decay data from financial-news-scoring API, send to Novita
(qwen3-max) for analysis, print result to stdout.

Usage:
    python simple_completion_call.py [SYMBOL ...] [-v]
    python simple_completion_call.py JPY -v
    python simple_completion_call.py JPY USD

Requires: NOVITA_API_KEY in env. News-agent API must be running at localhost:8000.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from openai import OpenAI

BASE_URL = "http://localhost:8000"
NOVITA_BASE_URL = "https://api.novita.ai/v3/openai"
MODEL = "qwen/qwen3-max"
HOURS = (72, 48, 24)


def log_err(msg: str) -> None:
    print(msg, file=sys.stderr)


def log_verbose(verbose: bool, msg: str) -> None:
    if verbose:
        print(msg, file=sys.stdout)


def fetch_trend_decay(symbol: str, hours: int) -> dict:
    url = f"{BASE_URL}/v1/news/currencies/{symbol}/hourly-trend-decay?hours={hours}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def load_prompt_template() -> str:
    script_dir = Path(__file__).resolve().parent
    path = script_dir / "final_prompt.yaml"
    with open(path) as f:
        return f.read()


def build_prompt(symbol: str, combined_data: dict) -> str:
    template = load_prompt_template()
    json_str = json.dumps(combined_data, indent=2)
    # Replace placeholder with actual data
    template = template.replace(
        "[Insert full JSON payload here, combining 72h, 48h, 24h responses if multiple calls]",
        json_str,
    )
    # Fix symbol reference
    template = template.replace("(here: JPY)", f"(here: {symbol})")
    return template


def analyze(symbol: str, verbose: bool = False) -> str | None:
    combined = {}
    for h in HOURS:
        try:
            log_verbose(verbose, f"Fetching {symbol} {h}h...")
            data = fetch_trend_decay(symbol, h)
            combined[f"{h}h"] = data
            log_verbose(verbose, f"  OK: {len(data.get('rows', []))} rows")
        except urllib.error.HTTPError as e:
            log_err(f"Error fetching {symbol} {h}h: HTTP {e.code} {e.reason}")
            return None
        except urllib.error.URLError as e:
            log_err(f"Error fetching {symbol} {h}h: {e.reason}")
            return None
        except json.JSONDecodeError as e:
            log_err(f"Error parsing {symbol} {h}h response: {e}")
            return None

    api_key = os.environ.get("NOVITA_API_KEY")
    if not api_key:
        log_err("NOVITA_API_KEY not set")
        return None

    log_verbose(verbose, f"Building prompt for {symbol}...")
    prompt = build_prompt(symbol, combined)
    log_verbose(verbose, f"  Prompt length: {len(prompt)} chars")

    log_verbose(verbose, f"Calling Novita ({MODEL})...")
    client = OpenAI(base_url=NOVITA_BASE_URL, api_key=api_key)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2048,
        )
        content = resp.choices[0].message.content or ""
        log_verbose(verbose, f"  Response: {len(content)} chars")
        return content
    except Exception as e:
        log_err(f"Novita API error: {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch trend-decay data, analyze via Novita qwen3-max, print to stdout."
    )
    parser.add_argument(
        "symbols",
        nargs="*",
        default=["JPY"],
        metavar="SYMBOL",
        help="Currency symbol(s), e.g. JPY USD (default: JPY)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log progress to stdout",
    )
    args = parser.parse_args()
    symbols = args.symbols or ["JPY"]

    had_error = False
    for symbol in symbols:
        symbol = symbol.upper()
        if len(symbols) > 1:
            print(f"\n--- {symbol} ---\n")

        result = analyze(symbol, verbose=args.verbose)
        if result is not None:
            print(result)
        else:
            log_err(f"Skipping {symbol} due to errors above.")
            had_error = True

    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
