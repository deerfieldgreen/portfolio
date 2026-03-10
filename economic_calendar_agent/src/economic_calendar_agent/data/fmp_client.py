"""Async Financial Modeling Prep (FMP) API client.

Multi-layer caching strategy:
- L1: In-memory TTLCache (per-process)
- L2: Redis (shared across instances)
- Adaptive TTL based on event proximity
- Circuit breaker for resilience
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from aiolimiter import AsyncLimiter
from cachetools import TTLCache

from ..config import Settings
from .redis_cache import RedisCache

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Simple circuit breaker for API failures."""

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failures = 0
        self.last_failure_time: Optional[datetime] = None
        self.is_open = False

    def record_success(self) -> None:
        """Record successful request."""
        self.failures = 0
        self.is_open = False

    def record_failure(self) -> None:
        """Record failed request."""
        self.failures += 1
        self.last_failure_time = datetime.utcnow()

        if self.failures >= self.failure_threshold:
            self.is_open = True
            logger.warning(
                "Circuit breaker opened",
                extra={"failures": self.failures, "threshold": self.failure_threshold},
            )

    def should_allow_request(self) -> bool:
        """Check if request should be allowed."""
        if not self.is_open:
            return True

        # Check if timeout has passed
        if self.last_failure_time:
            elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
            if elapsed >= self.timeout_seconds:
                logger.info("Circuit breaker reset after timeout")
                self.is_open = False
                self.failures = 0
                return True

        return False


class FMPClient:
    """Async FMP API client with caching and rate limiting."""

    def __init__(self, settings: Settings, redis_cache: Optional[RedisCache] = None):
        """Initialize FMP client.

        Args:
            settings: Application settings
            redis_cache: Optional Redis cache instance for L2 caching
        """
        self.settings = settings
        self.base_url = settings.fmp_base_url
        self.api_key = settings.fmp_api_key.get_secret_value()

        # L1 cache: in-memory (max 1000 entries)
        self._l1_cache: TTLCache = TTLCache(maxsize=1000, ttl=300)

        # L2 cache: Redis (optional)
        self._l2_cache = redis_cache

        # Rate limiter: 750 requests per minute (Premium tier)
        self._rate_limiter = AsyncLimiter(
            max_rate=settings.fmp_rate_limit_per_min,
            time_period=60,
        )

        # Circuit breaker
        self._circuit_breaker = CircuitBreaker()

        # HTTP client (created on first use)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                http2=True,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _cache_key(self, endpoint: str, params: dict[str, Any]) -> str:
        """Generate cache key from endpoint and params."""
        # Sort params for consistent key generation
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        key_str = f"{endpoint}?{param_str}"
        key_hash = hashlib.md5(key_str.encode()).hexdigest()
        return f"econ:fmp:{key_hash}"

    def _compute_ttl(self, data: Any) -> int:
        """Compute adaptive TTL based on data content.

        Strategy:
        - Events >24h away: 3600s (1 hour)
        - Events 1-24h away: 300s (5 min)
        - Events <1h away: 60s (1 min)
        - Just-released data: bypass cache (0s)
        - Historical actuals: 86400s (24 hours)
        """
        # Default TTL
        default_ttl = 3600

        # Try to extract event datetime if present
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if isinstance(first_item, dict) and "date" in first_item:
                try:
                    event_time_str = first_item.get("date")
                    event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
                    now = datetime.utcnow().replace(tzinfo=event_time.tzinfo)

                    time_until = (event_time - now).total_seconds() / 3600  # hours

                    if time_until < 0:
                        # Past event — cache for 24 hours
                        return 86400
                    elif time_until < 1:
                        # Within 1 hour — short TTL
                        return 60
                    elif time_until < 24:
                        # 1-24 hours — medium TTL
                        return 300
                    else:
                        # >24 hours — long TTL
                        return 3600
                except Exception:
                    pass  # Fallback to default

        return default_ttl

    async def _fetch_with_cache(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        bypass_cache: bool = False,
    ) -> Any:
        """Fetch data with multi-layer caching.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            bypass_cache: If True, skip cache and fetch fresh

        Returns:
            API response data
        """
        if params is None:
            params = {}

        # Always include API key
        params["apikey"] = self.api_key

        # Generate cache key
        cache_key = self._cache_key(endpoint, params)

        # Check circuit breaker
        if not self._circuit_breaker.should_allow_request():
            raise RuntimeError("Circuit breaker is open — API temporarily unavailable")

        # L1 cache check
        if not bypass_cache and cache_key in self._l1_cache:
            logger.debug("L1 cache hit", extra={"endpoint": endpoint})
            return self._l1_cache[cache_key]

        # L2 cache check (Redis)
        if not bypass_cache and self._l2_cache:
            cached_data = await self._l2_cache.get_json(cache_key)
            if cached_data is not None:
                logger.debug("L2 cache hit", extra={"endpoint": endpoint})
                # Populate L1 for faster subsequent access
                self._l1_cache[cache_key] = cached_data
                return cached_data

        # Cache miss — fetch from API
        try:
            async with self._rate_limiter:
                client = await self._get_client()
                url = f"{self.base_url}/{endpoint}"

                logger.debug(
                    "FMP API request",
                    extra={"url": url, "params": {k: v for k, v in params.items() if k != "apikey"}},
                )

                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # Record success
                self._circuit_breaker.record_success()

                # Compute TTL and cache
                ttl = self._compute_ttl(data)
                if ttl > 0:
                    self._l1_cache[cache_key] = data
                    if self._l2_cache:
                        await self._l2_cache.set_json(cache_key, data, ttl)

                return data

        except httpx.HTTPStatusError as e:
            self._circuit_breaker.record_failure()
            logger.error(
                "FMP API HTTP error",
                extra={"endpoint": endpoint, "status": e.response.status_code, "error": str(e)},
            )
            raise
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("FMP API error", extra={"endpoint": endpoint, "error": str(e)})
            raise

    async def fetch_calendar(
        self,
        from_date: datetime,
        to_date: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch economic calendar events for a date range.

        FMP has a 3-month maximum range, so this method handles pagination.

        Args:
            from_date: Start date (inclusive)
            to_date: End date (inclusive)

        Returns:
            List of economic events
        """
        all_events = []
        current_start = from_date

        while current_start < to_date:
            # FMP max range: 3 months
            current_end = min(current_start + timedelta(days=90), to_date)

            params = {
                "from": current_start.strftime("%Y-%m-%d"),
                "to": current_end.strftime("%Y-%m-%d"),
            }

            try:
                events = await self._fetch_with_cache("economic_calendar", params)
                if isinstance(events, list):
                    all_events.extend(events)
                    logger.info(
                        "Fetched calendar events",
                        extra={
                            "from": params["from"],
                            "to": params["to"],
                            "count": len(events),
                        },
                    )
            except Exception as e:
                logger.error(
                    "Failed to fetch calendar chunk",
                    extra={"from": params["from"], "to": params["to"], "error": str(e)},
                )
                # Continue with next chunk

            current_start = current_end + timedelta(days=1)

        return all_events

    async def fetch_upcoming_events(
        self,
        hours_ahead: int = 48,
    ) -> list[dict[str, Any]]:
        """Fetch upcoming economic events.

        Args:
            hours_ahead: How many hours ahead to look

        Returns:
            List of upcoming events
        """
        now = datetime.utcnow()
        to_date = now + timedelta(hours=hours_ahead)

        return await self.fetch_calendar(now, to_date)

    async def fetch_indicator(
        self,
        name: str,
        country: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch historical data for a specific economic indicator.

        Args:
            name: Indicator name (e.g., "CPI", "GDP")
            country: Optional country code filter

        Returns:
            List of historical indicator data
        """
        endpoint = f"economic_indicator/{name}"
        params = {}
        if country:
            params["country"] = country

        return await self._fetch_with_cache(endpoint, params)
