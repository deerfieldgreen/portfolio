"""Relevance matrix: static event×pair relevance scores.

Based on Andersen et al. (2003) — empirical correlation between economic
indicators and FX pair volatility. Scores range from 0.0 (no correlation)
to 1.0 (strong correlation).
"""
from __future__ import annotations

from typing import Optional


# Static relevance matrix: event_type -> {pair: score}
# Based on literature + market observation
_RELEVANCE_MATRIX: dict[str, dict[str, float]] = {
    # US Events
    "FOMC": {
        "USDJPY": 0.98,
        "EURUSD": 0.95,
        "GBPUSD": 0.90,
        "AUDUSD": 0.75,
    },
    "NFP": {
        "USDJPY": 0.95,
        "EURUSD": 0.90,
        "GBPUSD": 0.85,
        "AUDUSD": 0.60,
    },
    "CPI": {
        "USDJPY": 0.90,
        "EURUSD": 0.88,
        "GBPUSD": 0.82,
        "AUDUSD": 0.55,
    },
    "GDP": {
        "USDJPY": 0.85,
        "EURUSD": 0.80,
        "GBPUSD": 0.75,
        "AUDUSD": 0.55,
    },
    "UNEMPLOYMENT": {
        "USDJPY": 0.80,
        "EURUSD": 0.75,
        "GBPUSD": 0.70,
        "AUDUSD": 0.50,
    },
    "RETAIL_SALES": {
        "USDJPY": 0.75,
        "EURUSD": 0.70,
        "GBPUSD": 0.65,
        "AUDUSD": 0.45,
    },
    # Euro Area Events
    "ECB": {
        "USDJPY": 0.50,
        "EURUSD": 0.95,
        "GBPUSD": 0.55,
        "AUDUSD": 0.40,
    },
    "EU_CPI": {
        "USDJPY": 0.35,
        "EURUSD": 0.90,
        "GBPUSD": 0.50,
        "AUDUSD": 0.30,
    },
    "EU_GDP": {
        "USDJPY": 0.30,
        "EURUSD": 0.85,
        "GBPUSD": 0.45,
        "AUDUSD": 0.30,
    },
    # UK Events
    "BOE": {
        "USDJPY": 0.30,
        "EURUSD": 0.45,
        "GBPUSD": 0.95,
        "AUDUSD": 0.25,
    },
    "UK_CPI": {
        "USDJPY": 0.25,
        "EURUSD": 0.40,
        "GBPUSD": 0.88,
        "AUDUSD": 0.20,
    },
    "UK_GDP": {
        "USDJPY": 0.20,
        "EURUSD": 0.35,
        "GBPUSD": 0.82,
        "AUDUSD": 0.18,
    },
    # Australia Events
    "RBA": {
        "USDJPY": 0.20,
        "EURUSD": 0.15,
        "GBPUSD": 0.15,
        "AUDUSD": 0.95,
    },
    "AU_CPI": {
        "USDJPY": 0.15,
        "EURUSD": 0.12,
        "GBPUSD": 0.12,
        "AUDUSD": 0.88,
    },
    "AU_GDP": {
        "USDJPY": 0.15,
        "EURUSD": 0.10,
        "GBPUSD": 0.10,
        "AUDUSD": 0.85,
    },
    # China/Japan Events (commodity linkage to AUD)
    "CN_PMI": {
        "USDJPY": 0.35,
        "EURUSD": 0.25,
        "GBPUSD": 0.20,
        "AUDUSD": 0.80,
    },
    "JP_CPI": {
        "USDJPY": 0.85,
        "EURUSD": 0.30,
        "GBPUSD": 0.25,
        "AUDUSD": 0.20,
    },
    "BOJ": {
        "USDJPY": 0.95,
        "EURUSD": 0.35,
        "GBPUSD": 0.30,
        "AUDUSD": 0.25,
    },
    # US Macro
    "PCE": {
        "USDJPY": 0.90,
        "EURUSD": 0.85,
        "GBPUSD": 0.80,
        "AUDUSD": 0.55,
    },
    "PERSONAL_SPENDING": {
        "USDJPY": 0.75,
        "EURUSD": 0.70,
        "GBPUSD": 0.65,
        "AUDUSD": 0.45,
    },
    "CONSUMER_CONFIDENCE": {
        "USDJPY": 0.70,
        "EURUSD": 0.65,
        "GBPUSD": 0.60,
        "AUDUSD": 0.40,
    },
    "DURABLE_GOODS": {
        "USDJPY": 0.78,
        "EURUSD": 0.72,
        "GBPUSD": 0.68,
        "AUDUSD": 0.45,
    },
    "ISM_PMI": {
        "USDJPY": 0.82,
        "EURUSD": 0.78,
        "GBPUSD": 0.72,
        "AUDUSD": 0.50,
    },
    "PPI": {
        "USDJPY": 0.78,
        "EURUSD": 0.75,
        "GBPUSD": 0.70,
        "AUDUSD": 0.48,
    },
    "TRADE_BALANCE": {
        "USDJPY": 0.72,
        "EURUSD": 0.68,
        "GBPUSD": 0.60,
        "AUDUSD": 0.55,
    },
    "HOUSING": {
        "USDJPY": 0.60,
        "EURUSD": 0.55,
        "GBPUSD": 0.50,
        "AUDUSD": 0.35,
    },
    "JOBLESS_CLAIMS": {
        "USDJPY": 0.72,
        "EURUSD": 0.68,
        "GBPUSD": 0.62,
        "AUDUSD": 0.42,
    },
    # Japan
    "TANKAN": {
        "USDJPY": 0.82,
        "EURUSD": 0.30,
        "GBPUSD": 0.25,
        "AUDUSD": 0.20,
    },
    # Generic central bank (unknown country) — scores 0.0 intentionally absent
    "INTEREST_RATE": {},
}

# Fuzzy matching: FMP event names → canonical event types
# FMP uses inconsistent naming (spaces, dashes, abbreviations)
_EVENT_NAME_MAPPING: dict[str, str] = {
    # FOMC variations
    "fomc": "FOMC",
    "federal open market committee": "FOMC",
    "fed rate decision": "FOMC",
    # NFP variations
    "non-farm payrolls": "NFP",
    "nonfarm payrolls": "NFP",
    "total nonfarm payroll": "NFP",
    "nfp": "NFP",
    # CPI variations
    "consumer price index": "CPI",
    "cpi": "CPI",
    "inflation rate": "CPI",
    "core cpi": "CPI",
    # GDP variations
    "gross domestic product": "GDP",
    "gdp": "GDP",
    "gdp growth rate": "GDP",
    # Unemployment
    "unemployment rate": "UNEMPLOYMENT",
    # Retail Sales
    "retail sales": "RETAIL_SALES",
    "advance retail sales": "RETAIL_SALES",
    # ECB
    "ecb": "ECB",
    "european central bank": "ECB",
    # BOE
    "boe": "BOE",
    "bank of england": "BOE",
    # RBA
    "rba": "RBA",
    "reserve bank of australia": "RBA",
    # BOJ
    "boj": "BOJ",
    "bank of japan": "BOJ",
    # China PMI
    "china pmi": "CN_PMI",
    "cn pmi": "CN_PMI",
    # PCE / Personal spending
    "pce price index": "PCE",
    "core pce": "PCE",
    "personal consumption expenditures": "PCE",
    "personal spending": "PERSONAL_SPENDING",
    "personal income": "PERSONAL_SPENDING",
    # Consumer confidence
    "consumer confidence": "CONSUMER_CONFIDENCE",
    "consumer sentiment": "CONSUMER_CONFIDENCE",
    # Durable goods
    "durable goods": "DURABLE_GOODS",
    "durable goods orders": "DURABLE_GOODS",
    # ISM
    "ism manufacturing": "ISM_PMI",
    "ism services": "ISM_PMI",
    # PPI
    "producer price index": "PPI",
    "ppi": "PPI",
    # Trade
    "trade balance": "TRADE_BALANCE",
    # Housing
    "housing starts": "HOUSING",
    "building permits": "HOUSING",
    # Japan
    "tankan": "TANKAN",
    # Jobless claims
    "initial jobless claims": "JOBLESS_CLAIMS",
    "jobless claims": "JOBLESS_CLAIMS",
}

# Country code -> central bank event type for "interest rate decision" disambiguation
_COUNTRY_CENTRAL_BANK: dict[str, str] = {
    "US": "FOMC",
    "EU": "ECB",
    "DE": "ECB",
    "FR": "ECB",
    "IT": "ECB",
    "ES": "ECB",
    "NL": "ECB",
    "BE": "ECB",
    "AT": "ECB",
    "FI": "ECB",
    "IE": "ECB",
    "PT": "ECB",
    "GR": "ECB",
    "GB": "BOE",
    "UK": "BOE",
    "JP": "BOJ",
    "AU": "RBA",
    "NZ": "RBNZ",
    "CA": "BOC",
    "CH": "SNB",
    "CN": "PBOC",
}

# Country code -> PMI event type for "manufacturing pmi" disambiguation
_COUNTRY_PMI: dict[str, str] = {
    "CN": "CN_PMI",
    "US": "ISM_PMI",
}


def normalize_event_name(event_name: str, country: Optional[str] = None) -> str:
    """Normalize FMP event name to canonical event type.

    Uses country-aware disambiguation for generic event names like
    "Interest Rate Decision" and "Manufacturing PMI".

    Args:
        event_name: Raw event name from FMP
        country: Optional country code for disambiguation

    Returns:
        Canonical event type (e.g., "NFP", "CPI", "FOMC")
    """
    key = event_name.lower().strip()

    # Country-aware: interest rate decision -> central bank by country
    if "interest rate" in key or "rate decision" in key:
        if country and country in _COUNTRY_CENTRAL_BANK:
            return _COUNTRY_CENTRAL_BANK[country]
        return "INTEREST_RATE"  # Generic, no matrix entry -> scores 0.0

    # Country-aware: manufacturing pmi -> gated on country
    if "manufacturing pmi" in key:
        if country and country in _COUNTRY_PMI:
            return _COUNTRY_PMI[country]
        return event_name.upper().replace(" ", "_")

    # Direct lookup
    if key in _EVENT_NAME_MAPPING:
        canonical = _EVENT_NAME_MAPPING[key]
        # Add country prefix for non-US inflation and GDP data
        if country and country != "US":
            if canonical in ("CPI", "GDP"):
                return f"{country}_{canonical}"
            elif canonical in ("ECB", "BOE", "RBA", "BOJ"):
                return canonical  # Already country-specific
        return canonical

    # Partial matching with country context
    for pattern, canonical in _EVENT_NAME_MAPPING.items():
        if pattern in key:
            if country and country != "US" and canonical in ("CPI", "GDP"):
                return f"{country}_{canonical}"
            return canonical

    # Fallback: return original name uppercased
    return event_name.upper().replace(" ", "_")


def get_relevance(event_type: str, pair: str) -> float:
    """Get relevance score for an event type and FX pair.

    Args:
        event_type: Canonical event type (e.g., "NFP", "FOMC")
        pair: FX pair (e.g., "USDJPY", "EURUSD")

    Returns:
        Relevance score [0.0, 1.0], or 0.0 if not found
    """
    pair_scores = _RELEVANCE_MATRIX.get(event_type, {})
    return pair_scores.get(pair, 0.0)


def get_affected_pairs(
    event_type: str,
    min_score: float = 0.3,
) -> list[tuple[str, float]]:
    """Get all FX pairs affected by an event type above a threshold.

    Args:
        event_type: Canonical event type
        min_score: Minimum relevance score to include

    Returns:
        List of (pair, score) tuples, sorted by score descending
    """
    pair_scores = _RELEVANCE_MATRIX.get(event_type, {})
    filtered = [(pair, score) for pair, score in pair_scores.items() if score >= min_score]
    return sorted(filtered, key=lambda x: x[1], reverse=True)


def get_all_event_types() -> list[str]:
    """Get all canonical event types in the relevance matrix."""
    return list(_RELEVANCE_MATRIX.keys())


def load_relevance_overrides(overrides: dict[str, dict[str, float]]) -> None:
    """Load dynamic relevance scores from ClickHouse or ML calibration.

    Args:
        overrides: Dict of event_type -> {pair: score} to merge into matrix
    """
    for event_type, pair_scores in overrides.items():
        if event_type not in _RELEVANCE_MATRIX:
            _RELEVANCE_MATRIX[event_type] = {}
        _RELEVANCE_MATRIX[event_type].update(pair_scores)
