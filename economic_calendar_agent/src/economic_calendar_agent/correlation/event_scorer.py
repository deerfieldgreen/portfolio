"""Composite event scoring engine.

Combines relevance, impact, surprise, and time decay into a unified score
for each event×pair combination. The primary integration point for all
correlation logic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import re

from ..data.fx_pair_map import get_pair_countries
from ..models.events import EconomicEvent, ScoredEvent
from ..models.schemas import ImpactLevel, MacroRiskLevel
from . import relevance_matrix, surprise_factor, time_decay

# Central bank event types that are valid cross-correlations
_CENTRAL_BANK_TYPES = {"FOMC", "ECB", "BOE", "BOJ", "RBA", "RBNZ", "BOC", "SNB", "PBOC"}
# Pattern for country-prefixed event types (e.g., CN_PMI, JP_CPI, EU_GDP)
_COUNTRY_PREFIX_RE = re.compile(r"^[A-Z]{2}_")


# Impact level weights (relative importance)
_IMPACT_WEIGHTS = {
    ImpactLevel.HIGH: 1.0,
    ImpactLevel.MEDIUM: 0.6,
    ImpactLevel.LOW: 0.3,
    ImpactLevel.NONE: 0.1,
}


def score_event(
    event: EconomicEvent,
    pairs: list[str],
    current_time: Optional[datetime] = None,
    historical_std: Optional[float] = None,
) -> ScoredEvent:
    """Score a single economic event across multiple FX pairs.

    Composite formula:
        Score(event, pair, t) = Relevance(event, pair) ×
                                ImpactWeight(event) ×
                                |SurpriseZScore(event)| ×
                                DecayFactor(event, t)

    Args:
        event: EconomicEvent to score
        pairs: List of FX pairs to score against
        current_time: Current timestamp (defaults to now UTC)
        historical_std: Historical std dev for surprise calculation

    Returns:
        ScoredEvent with scores for each pair
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # Ensure event datetime is timezone-aware for comparison
    event_dt = event.event_datetime
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)

    # Calculate time since release (negative if future event)
    time_delta = (current_time - event_dt).total_seconds() / 60.0
    minutes_since_release = time_delta if event.actual is not None else None

    # Get base components
    impact_weight = _IMPACT_WEIGHTS.get(event.impact, 0.5)

    # Calculate surprise z-score if data available
    surprise_zscore = None
    surprise_dir = None
    surprise_multiplier = 1.0

    if event.actual is not None and event.estimate is not None and historical_std:
        surprise_zscore = surprise_factor.compute_surprise_zscore(
            event.actual, event.estimate, historical_std
        )
        surprise_dir = surprise_factor.classify_surprise(surprise_zscore)
        # Use absolute z-score as multiplier (capped at 3.0 for stability)
        surprise_multiplier = min(abs(surprise_zscore), 3.0)

    # Calculate time decay / anticipation weight
    decay_factor = 1.0
    if minutes_since_release is not None and minutes_since_release > 0:
        decay_factor = time_decay.remaining_impact_pct(
            event.event_type, minutes_since_release
        )
    else:
        # Future event: apply anticipation weight
        minutes_until = -time_delta
        if minutes_until > 0:
            decay_factor = time_decay.anticipation_weight(minutes_until)

    # Compute relevance and composite scores per pair
    relevance_scores = {}
    composite_scores = {}

    for pair in pairs:
        relevance = relevance_matrix.get_relevance(event.event_type, pair)

        # Country gating: if event's country is NOT a constituent of this
        # pair, zero relevance unless it's a curated cross-correlation.
        # Cross-correlations are: central bank types (ECB, BOJ, etc.) or
        # country-prefixed types (CN_PMI, JP_CPI) which indicate the
        # normalization already mapped country-specific impact.
        pair_countries = get_pair_countries(pair)
        if event.country not in pair_countries:
            is_cross_correlation = (
                event.event_type in _CENTRAL_BANK_TYPES
                or _COUNTRY_PREFIX_RE.match(event.event_type) is not None
            )
            if not is_cross_correlation or relevance == 0.0:
                relevance = 0.0

        relevance_scores[pair] = relevance

        # Composite score
        composite = relevance * impact_weight * surprise_multiplier * decay_factor
        composite_scores[pair] = composite

    return ScoredEvent(
        event=event,
        relevance_scores=relevance_scores,
        surprise_zscore=surprise_zscore,
        surprise_direction=surprise_dir,
        time_decay_factor=decay_factor,
        composite_scores=composite_scores,
        minutes_since_release=minutes_since_release,
    )


def score_upcoming_events(
    events: list[EconomicEvent],
    pairs: list[str],
    current_time: Optional[datetime] = None,
) -> list[ScoredEvent]:
    """Score multiple upcoming events.

    For unreleased events (no actual value), uses expected surprise
    magnitude based on historical volatility.

    Args:
        events: List of EconomicEvents
        pairs: FX pairs to score against
        current_time: Current timestamp

    Returns:
        List of ScoredEvents
    """
    scored_events = []

    for event in events:
        # For upcoming events, use default historical_std = 1.0
        # (can be refined with actual historical data from ClickHouse)
        historical_std = 1.0 if event.actual is None else None

        scored = score_event(
            event=event,
            pairs=pairs,
            current_time=current_time,
            historical_std=historical_std,
        )
        scored_events.append(scored)

    return scored_events


def aggregate_macro_risk(
    scored_events: list[ScoredEvent],
    pairs: list[str],
) -> dict[str, MacroRiskLevel]:
    """Aggregate macro risk level per pair from scored events.

    Risk levels:
    - HIGH: Any event with score > 0.7 within 30 min
    - MEDIUM: Sum of scores > 1.5 within 2 hours
    - LOW: Otherwise

    Args:
        scored_events: List of ScoredEvents
        pairs: FX pairs to assess

    Returns:
        Dict of pair -> MacroRiskLevel
    """
    risk_levels = {}

    for pair in pairs:
        high_impact_imminent = False
        medium_impact_sum = 0.0

        for scored_event in scored_events:
            score = scored_event.get_score(pair)
            minutes_since = scored_event.minutes_since_release

            # Check for high impact within 30 min
            if minutes_since is not None:
                if -30 <= minutes_since <= 30 and score > 0.7:
                    high_impact_imminent = True
                    break

                # Sum scores within 2 hours for medium risk
                if -120 <= minutes_since <= 120:
                    medium_impact_sum += score
            else:
                # Future event without release time — include in sum
                medium_impact_sum += score

        # Determine risk level
        if high_impact_imminent:
            risk_levels[pair] = MacroRiskLevel.HIGH
        elif medium_impact_sum > 1.5:
            risk_levels[pair] = MacroRiskLevel.MEDIUM
        else:
            risk_levels[pair] = MacroRiskLevel.LOW

    return risk_levels


def format_for_llm(scored_events: list[ScoredEvent], pairs: list[str]) -> str:
    """Format scored events as structured markdown for LLM reasoning.

    Args:
        scored_events: List of ScoredEvents
        pairs: FX pairs included

    Returns:
        Markdown-formatted string
    """
    if not scored_events:
        return "No economic events in the analysis window."

    lines = ["# Economic Calendar Analysis\n"]

    # Group by time proximity
    imminent = []
    upcoming = []
    recent = []

    for scored in scored_events:
        if scored.minutes_since_release is None:
            upcoming.append(scored)
        elif scored.minutes_since_release < 0:
            upcoming.append(scored)
        elif scored.minutes_since_release <= 30:
            imminent.append(scored)
        elif scored.minutes_since_release <= 240:  # 4 hours
            recent.append(scored)

    # High impact imminent
    if imminent:
        lines.append("## 🔴 HIGH IMPACT IMMINENT (Within 30 min)\n")
        for scored in imminent:
            lines.append(_format_event_line(scored, pairs))
        lines.append("")

    # Upcoming events
    if upcoming:
        lines.append("## 📅 Upcoming Events\n")
        for scored in sorted(upcoming, key=lambda s: s.event.event_datetime):
            lines.append(_format_event_line(scored, pairs))
        lines.append("")

    # Recent releases
    if recent:
        lines.append("## 📊 Recent Releases (Last 4 hours)\n")
        for scored in sorted(recent, key=lambda s: s.event.event_datetime, reverse=True):
            lines.append(_format_event_line(scored, pairs))
        lines.append("")

    # Macro risk summary
    risk_levels = aggregate_macro_risk(imminent + upcoming + recent, pairs)
    lines.append("## ⚡ Trading Implications\n")
    for pair in pairs:
        risk = risk_levels.get(pair, MacroRiskLevel.LOW)
        emoji = "🔴" if risk == MacroRiskLevel.HIGH else "🟡" if risk == MacroRiskLevel.MEDIUM else "🟢"
        lines.append(f"- **{pair}**: {emoji} {risk.value} macro risk")
    lines.append("")

    return "\n".join(lines)


def _format_event_line(scored: ScoredEvent, pairs: list[str]) -> str:
    """Format a single scored event as a markdown line."""
    event = scored.event
    time_str = event.event_datetime.strftime("%Y-%m-%d %H:%M UTC")

    # Event header
    line = f"### {event.country} - {event.event_name} ({time_str})\n"

    # Data values
    if event.actual is not None:
        line += f"- **Actual**: {event.actual}"
        if scored.surprise_direction:
            line += f" ({scored.surprise_direction.value}, z={scored.surprise_zscore:.2f})"
        line += "\n"
    if event.estimate is not None:
        line += f"- **Forecast**: {event.estimate}\n"
    if event.previous is not None:
        line += f"- **Previous**: {event.previous}\n"

    # Impact and decay/anticipation label
    is_future = scored.minutes_since_release is None or scored.minutes_since_release < 0
    decay_label = "Anticipation" if is_future else "Remaining Impact"
    line += f"- **Impact**: {event.impact.value}, {decay_label}: {scored.time_decay_factor:.1%}\n"

    # Scores per pair
    top_pairs = sorted(
        [(pair, scored.composite_scores.get(pair, 0.0)) for pair in pairs],
        key=lambda x: x[1],
        reverse=True,
    )[:3]  # Top 3 affected pairs

    if top_pairs:
        line += "- **Affected Pairs**: "
        line += ", ".join([f"{pair} ({score:.2f})" for pair, score in top_pairs if score > 0.1])
        line += "\n"

    line += "\n"
    return line
