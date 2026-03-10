"""Economic calendar tool node for LangGraph agent.

Primary tool that analyzes upcoming and recent economic events,
scores them using the correlation engine, and provides structured
context for LLM reasoning.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from ...config import get_settings
from ...correlation import event_scorer
from ...data.fmp_client import FMPClient
from ...data.redis_cache import RedisCache
from ...models.events import EconomicEvent
from ...models.schemas import (
    EconomicContext,
    EconomicEventOutput,
    ImpactLevel,
)
from ..state import FXTradingState

logger = logging.getLogger(__name__)


# ── Impact overrides for known FMP misclassifications ──
# Only upgrades impact (never downgrades). Keyed by (country, regex pattern).
_IMPACT_OVERRIDES: list[tuple[str, str, ImpactLevel]] = [
    # US
    ("US", r"core pce|pce price index", ImpactLevel.HIGH),
    ("US", r"personal spending|personal income", ImpactLevel.HIGH),
    ("US", r"durable goods", ImpactLevel.HIGH),
    # Japan
    ("JP", r"core cpi|(?<!\w)cpi(?!\w)", ImpactLevel.HIGH),
    ("JP", r"boj|tankan|gdp", ImpactLevel.HIGH),
    # Germany
    ("DE", r"consumer confidence", ImpactLevel.HIGH),
]

# Pre-compile patterns
_COMPILED_IMPACT_OVERRIDES = [
    (country, re.compile(pattern, re.IGNORECASE), level)
    for country, pattern, level in _IMPACT_OVERRIDES
]


async def economic_calendar_node(state: FXTradingState) -> dict:
    """Fetch and analyze economic calendar events.

    This is the primary tool node that:
    1. Fetches upcoming events from FMP API (or Redis cache)
    2. Scores events using correlation engine
    3. Aggregates macro risk per pair
    4. Formats structured output for LLM

    Args:
        state: Current agent state

    Returns:
        Dict with economic_context field populated
    """
    settings = get_settings()
    pairs = state.get("target_pairs", settings.target_pairs)

    logger.info(
        "Economic calendar node starting",
        extra={"pairs": pairs},
    )

    try:
        # Initialize clients
        redis_cache = RedisCache(settings.dragonfly_url)
        fmp_client = FMPClient(settings, redis_cache=redis_cache)

        # Check Redis for daily digest
        cache_key = f"econ:daily_digest:{datetime.utcnow().strftime('%Y-%m-%d')}"
        cached_context = await redis_cache.get_json(cache_key)

        if cached_context:
            logger.info("Using cached daily economic digest")
            economic_context = EconomicContext(**cached_context)
        else:
            # Fetch fresh data from FMP
            logger.info("Fetching fresh economic calendar from FMP")
            raw_events = await fmp_client.fetch_upcoming_events(
                hours_ahead=settings.pipeline_lookahead_hours
            )

            # Convert to domain models and deduplicate
            events = _deduplicate_events(_convert_fmp_events(raw_events))

            # Score events
            scored_events = event_scorer.score_upcoming_events(
                events=events,
                pairs=pairs,
            )

            # Filter out events irrelevant to requested pairs
            scored_events = [
                se for se in scored_events
                if max(se.composite_scores.get(p, 0.0) for p in pairs) >= 0.05
            ]

            # Aggregate risk
            risk_levels = event_scorer.aggregate_macro_risk(scored_events, pairs)

            # Find imminent high-impact events
            high_impact_imminent = [
                se
                for se in scored_events
                if se.is_high_impact() and (se.minutes_since_release or 0) >= -30
            ]

            # Format for LLM
            summary = event_scorer.format_for_llm(scored_events, pairs)

            # Build output
            economic_context = EconomicContext(
                timestamp=datetime.now(timezone.utc),
                events=[_convert_to_output(se) for se in scored_events],
                macro_risk=risk_levels,
                high_impact_imminent=[
                    _convert_to_output(se) for se in high_impact_imminent
                ],
                summary=summary,
                raw_data_summary=summary,
            )

            # Cache for 5 minutes
            await redis_cache.set_json(
                cache_key,
                economic_context.model_dump(mode="json"),
                ttl_seconds=300,
            )

        # Cleanup
        await fmp_client.close()
        await redis_cache.disconnect()

        logger.info(
            "Economic calendar node complete",
            extra={
                "events_count": len(economic_context.events),
                "high_impact_imminent": len(economic_context.high_impact_imminent),
            },
        )

        return {"economic_context": economic_context}

    except Exception as e:
        logger.error(
            "Economic calendar node failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        return {"error": f"Economic calendar error: {str(e)}"}


def _convert_fmp_events(raw_events: list[dict]) -> list[EconomicEvent]:
    """Convert FMP API response to EconomicEvent domain models.

    Args:
        raw_events: Raw FMP API response

    Returns:
        List of EconomicEvent objects
    """
    from ...correlation.relevance_matrix import normalize_event_name

    events = []

    for raw in raw_events:
        try:
            # Parse event datetime
            event_datetime_str = raw.get("date", "")
            event_datetime = datetime.fromisoformat(
                event_datetime_str.replace("Z", "+00:00")
            )

            # Normalize event name to canonical type
            country = raw.get("country", "US")
            event_type = normalize_event_name(raw.get("event", ""), country)

            # Parse impact level and apply overrides
            impact_str = raw.get("impact", "Low")
            impact = ImpactLevel(impact_str) if impact_str else ImpactLevel.LOW
            impact = _override_impact(country, raw.get("event", ""), impact)

            event = EconomicEvent(
                event_id=f"{country}-{event_type}-{event_datetime.isoformat()}",
                event_name=raw.get("event", "Unknown"),
                event_type=event_type,
                country=country,
                currency=raw.get("currency", "USD"),
                event_datetime=event_datetime,
                impact=impact,
                actual=raw.get("actual"),
                estimate=raw.get("estimate"),
                previous=raw.get("previous"),
            )

            events.append(event)

        except Exception as e:
            logger.warning(
                "Failed to parse FMP event",
                extra={"raw_event": raw, "error": str(e)},
            )
            continue

    return events


def _override_impact(
    country: str, event_name: str, fmp_impact: ImpactLevel
) -> ImpactLevel:
    """Apply impact overrides for known FMP misclassifications.

    Only upgrades impact — never downgrades.

    Args:
        country: Country code
        event_name: Raw FMP event name
        fmp_impact: Impact level from FMP

    Returns:
        Possibly upgraded ImpactLevel
    """
    _LEVEL_ORDER = {
        ImpactLevel.NONE: 0,
        ImpactLevel.LOW: 1,
        ImpactLevel.MEDIUM: 2,
        ImpactLevel.HIGH: 3,
    }

    best = fmp_impact
    for ovr_country, pattern, ovr_level in _COMPILED_IMPACT_OVERRIDES:
        if ovr_country == country and pattern.search(event_name):
            if _LEVEL_ORDER.get(ovr_level, 0) > _LEVEL_ORDER.get(best, 0):
                best = ovr_level

    return best


def _deduplicate_events(events: list[EconomicEvent]) -> list[EconomicEvent]:
    """Remove duplicate events from FMP response.

    Dedup key: (country, timestamp rounded to minute, normalized base indicator name).
    When duplicates collide, keep the one with actual data or the longer name.

    Args:
        events: List of EconomicEvent objects

    Returns:
        Deduplicated list
    """
    # Normalization: strip title words, collapse whitespace
    _TITLE_WORDS = re.compile(
        r"\b(president|governor|chairman|chair|vice|deputy|member)\b",
        re.IGNORECASE,
    )

    def _dedup_key(event: EconomicEvent) -> tuple:
        name = _TITLE_WORDS.sub("", event.event_name.lower())
        name = re.sub(r"\s+", " ", name).strip()
        ts_minute = event.event_datetime.replace(second=0, microsecond=0)
        return (event.country, ts_minute, name)

    seen: dict[tuple, EconomicEvent] = {}
    for event in events:
        key = _dedup_key(event)
        if key not in seen:
            seen[key] = event
        else:
            existing = seen[key]
            # Prefer the one with actual data
            if event.actual is not None and existing.actual is None:
                seen[key] = event
            # Tie-break: prefer longer name (more descriptive)
            elif len(event.event_name) > len(existing.event_name):
                seen[key] = event

    deduped = list(seen.values())
    removed = len(events) - len(deduped)
    if removed:
        logger.info(
            "Deduplicated events",
            extra={"original": len(events), "deduped": len(deduped), "removed": removed},
        )
    return deduped


def _convert_to_output(scored_event) -> EconomicEventOutput:
    """Convert ScoredEvent to EconomicEventOutput schema.

    Args:
        scored_event: ScoredEvent from correlation engine

    Returns:
        EconomicEventOutput for API/LLM consumption
    """
    event = scored_event.event

    return EconomicEventOutput(
        event_id=event.event_id,
        event_name=event.event_name,
        event_type=event.event_type,
        country=event.country,
        currency=event.currency,
        event_datetime=event.event_datetime,
        impact=event.impact,
        actual=event.actual,
        estimate=event.estimate,
        previous=event.previous,
        relevance_scores=scored_event.relevance_scores,
        surprise_zscore=scored_event.surprise_zscore,
        surprise_direction=scored_event.surprise_direction,
        time_decay_factor=scored_event.time_decay_factor,
        composite_scores=scored_event.composite_scores,
    )
