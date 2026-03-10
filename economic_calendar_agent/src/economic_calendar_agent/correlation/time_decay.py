"""Two-component exponential time decay model.

Implements fast + slow decay components to capture both immediate
price impact and gradual information absorption.

Based on Evans & Lyons (2005) microstructure research showing:
- Fast component: Order flow impact decays within minutes
- Slow component: Fundamental information persists for hours/days
"""
from __future__ import annotations

import math
from typing import Optional

from ..models.events import DecayParams


# Default decay parameters per event type
# Half-lives in minutes: time for impact to reach 50%
_DEFAULT_DECAY_PARAMS: dict[str, DecayParams] = {
    "FOMC": DecayParams(
        event_type="FOMC",
        fast_halflife_minutes=10.0,
        slow_halflife_minutes=240.0,  # 4 hours
        alpha=0.40,
    ),
    "NFP": DecayParams(
        event_type="NFP",
        fast_halflife_minutes=5.0,
        slow_halflife_minutes=60.0,  # 1 hour
        alpha=0.60,
    ),
    "CPI": DecayParams(
        event_type="CPI",
        fast_halflife_minutes=5.0,
        slow_halflife_minutes=90.0,  # 1.5 hours
        alpha=0.55,
    ),
    "GDP": DecayParams(
        event_type="GDP",
        fast_halflife_minutes=5.0,
        slow_halflife_minutes=60.0,
        alpha=0.55,
    ),
    "ECB": DecayParams(
        event_type="ECB",
        fast_halflife_minutes=10.0,
        slow_halflife_minutes=180.0,  # 3 hours
        alpha=0.40,
    ),
    "BOE": DecayParams(
        event_type="BOE",
        fast_halflife_minutes=10.0,
        slow_halflife_minutes=180.0,
        alpha=0.40,
    ),
    "RBA": DecayParams(
        event_type="RBA",
        fast_halflife_minutes=10.0,
        slow_halflife_minutes=120.0,  # 2 hours
        alpha=0.40,
    ),
    "BOJ": DecayParams(
        event_type="BOJ",
        fast_halflife_minutes=10.0,
        slow_halflife_minutes=240.0,
        alpha=0.40,
    ),
    # Default for unknown event types
    "_DEFAULT": DecayParams(
        event_type="_DEFAULT",
        fast_halflife_minutes=5.0,
        slow_halflife_minutes=60.0,
        alpha=0.50,
    ),
}


def get_decay_params(event_type: str) -> DecayParams:
    """Get decay parameters for an event type.

    Args:
        event_type: Canonical event type (e.g., "NFP", "FOMC")

    Returns:
        DecayParams for the event type, or default if not found
    """
    return _DEFAULT_DECAY_PARAMS.get(event_type, _DEFAULT_DECAY_PARAMS["_DEFAULT"])


def compute_decay(
    impact_initial: float,
    event_type: str,
    minutes_elapsed: float,
) -> float:
    """Compute time-decayed impact using two-component exponential model.

    Formula: Impact(t) = α × Impact₀ × e^(-λ_fast × t) +
                         (1-α) × Impact₀ × e^(-λ_slow × t)

    Where:
        λ_fast = ln(2) / fast_halflife
        λ_slow = ln(2) / slow_halflife

    Args:
        impact_initial: Initial impact magnitude
        event_type: Canonical event type
        minutes_elapsed: Time since event release (minutes)

    Returns:
        Time-decayed impact value
    """
    if minutes_elapsed < 0:
        return impact_initial  # Future event, no decay

    params = get_decay_params(event_type)

    # Convert half-lives to decay rates
    lambda_fast = math.log(2) / params.fast_halflife_minutes
    lambda_slow = math.log(2) / params.slow_halflife_minutes

    # Two-component decay
    fast_component = params.alpha * impact_initial * math.exp(-lambda_fast * minutes_elapsed)
    slow_component = (1 - params.alpha) * impact_initial * math.exp(-lambda_slow * minutes_elapsed)

    return fast_component + slow_component


def remaining_impact_pct(
    event_type: str,
    minutes_elapsed: float,
) -> float:
    """Calculate remaining impact as percentage of initial impact.

    Args:
        event_type: Canonical event type
        minutes_elapsed: Time since event release (minutes)

    Returns:
        Percentage of initial impact remaining (0.0-1.0)
    """
    return compute_decay(1.0, event_type, minutes_elapsed)


def minutes_until_threshold(
    event_type: str,
    threshold_pct: float = 0.1,
) -> float:
    """Calculate time until impact decays below threshold.

    Args:
        event_type: Canonical event type
        threshold_pct: Threshold percentage (0.0-1.0)

    Returns:
        Minutes until impact falls below threshold
    """
    params = get_decay_params(event_type)

    # Binary search for time when remaining_impact_pct < threshold
    low, high = 0.0, params.slow_halflife_minutes * 10  # Search up to 10 half-lives
    epsilon = 0.1  # Precision in minutes

    while high - low > epsilon:
        mid = (low + high) / 2
        impact = remaining_impact_pct(event_type, mid)

        if impact > threshold_pct:
            low = mid
        else:
            high = mid

    return high


def anticipation_weight(minutes_until_event: float) -> float:
    """Calculate anticipation weight for a future (not-yet-released) event.

    Piecewise linear curve reflecting increasing market focus as events
    approach:
        - Within 60 min:  1.0
        - 1-6 hours:      1.0 -> 0.6  (linear)
        - 6-24 hours:     0.6 -> 0.2  (linear)
        - 24-48 hours:    0.2 -> 0.05 (linear, floors at 0.05)

    Args:
        minutes_until_event: Positive minutes until event release

    Returns:
        Anticipation weight in [0.05, 1.0]
    """
    if minutes_until_event <= 60:
        return 1.0
    elif minutes_until_event <= 360:  # 6 hours
        # Linear 1.0 -> 0.6 over 300 minutes
        return 1.0 - 0.4 * (minutes_until_event - 60) / 300
    elif minutes_until_event <= 1440:  # 24 hours
        # Linear 0.6 -> 0.2 over 1080 minutes
        return 0.6 - 0.4 * (minutes_until_event - 360) / 1080
    elif minutes_until_event <= 2880:  # 48 hours
        # Linear 0.2 -> 0.05 over 1440 minutes
        return 0.2 - 0.15 * (minutes_until_event - 1440) / 1440
    else:
        return 0.05


def load_decay_overrides(overrides: dict[str, DecayParams]) -> None:
    """Load calibrated decay parameters from ClickHouse or ML optimization.

    Args:
        overrides: Dict of event_type -> DecayParams to merge
    """
    for event_type, params in overrides.items():
        _DEFAULT_DECAY_PARAMS[event_type] = params
