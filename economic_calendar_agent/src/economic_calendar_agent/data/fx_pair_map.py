"""FX pair to country mapping and central bank associations.

Maps country codes to affected FX pairs and identifies central bank events.
"""
from __future__ import annotations

# Country code -> FX pairs mapping
# Primary: countries whose currency is directly in the pair
# Central banks: monetary authorities affecting the pair
FX_PAIR_COUNTRY_MAP: dict[str, dict[str, list[str]]] = {
    "USDJPY": {
        "primary": ["US", "JP"],
        "central_banks": ["Fed", "BOJ", "FOMC"],
    },
    "EURUSD": {
        "primary": ["US", "EU", "DE", "FR", "IT", "ES"],
        "central_banks": ["Fed", "ECB", "FOMC"],
    },
    "GBPUSD": {
        "primary": ["US", "GB", "UK"],
        "central_banks": ["Fed", "BOE", "FOMC"],
    },
    "AUDUSD": {
        "primary": ["US", "AU", "CN"],  # China due to commodity linkage
        "central_banks": ["Fed", "RBA", "FOMC"],
    },
}

# Inverse mapping: country -> affected pairs
_COUNTRY_TO_PAIRS: dict[str, list[str]] = {}
for pair, data in FX_PAIR_COUNTRY_MAP.items():
    for country in data["primary"]:
        if country not in _COUNTRY_TO_PAIRS:
            _COUNTRY_TO_PAIRS[country] = []
        _COUNTRY_TO_PAIRS[country].append(pair)


def get_affected_pairs(country_code: str) -> list[str]:
    """Get all FX pairs affected by a country's economic events.

    Args:
        country_code: ISO country code (e.g., "US", "EU", "JP")

    Returns:
        List of affected FX pairs
    """
    return _COUNTRY_TO_PAIRS.get(country_code.upper(), [])


def get_pair_countries(pair: str) -> list[str]:
    """Get all countries whose events affect a specific FX pair.

    Args:
        pair: FX pair (e.g., "USDJPY")

    Returns:
        List of country codes
    """
    pair_data = FX_PAIR_COUNTRY_MAP.get(pair.upper(), {})
    return pair_data.get("primary", [])


def get_central_banks(pair: str) -> list[str]:
    """Get central banks that affect a specific FX pair.

    Args:
        pair: FX pair (e.g., "USDJPY")

    Returns:
        List of central bank identifiers
    """
    pair_data = FX_PAIR_COUNTRY_MAP.get(pair.upper(), {})
    return pair_data.get("central_banks", [])


def is_usd_event(country: str) -> bool:
    """Check if an event affects all USD pairs.

    Args:
        country: Country code

    Returns:
        True if US event (affects all pairs)
    """
    return country.upper() in ("US", "USA")


def is_central_bank_event(event_type: str) -> bool:
    """Check if an event is a central bank decision.

    Args:
        event_type: Canonical event type

    Returns:
        True if central bank event
    """
    central_bank_keywords = ["FOMC", "ECB", "BOE", "RBA", "BOJ", "Fed"]
    event_upper = event_type.upper()
    return any(keyword.upper() in event_upper for keyword in central_bank_keywords)


def get_all_pairs() -> list[str]:
    """Get all configured FX pairs."""
    return list(FX_PAIR_COUNTRY_MAP.keys())


def get_pair_symbol(pair: str) -> tuple[str, str]:
    """Split FX pair into base and quote currencies.

    Args:
        pair: FX pair (e.g., "USDJPY")

    Returns:
        Tuple of (base_currency, quote_currency)
    """
    pair_upper = pair.upper()
    if len(pair_upper) == 6:
        return pair_upper[:3], pair_upper[3:]
    else:
        raise ValueError(f"Invalid FX pair format: {pair}")
