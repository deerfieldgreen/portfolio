"""Dragonfly (Redis-compatible) L2 cache with adaptive TTL and jitter.

Provides shared caching layer across agent instances with
time-based expiration and pattern-based invalidation.
"""
from __future__ import annotations

import json
import logging
import random
from typing import Any, Callable, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisCache:
    """Async Redis cache client with adaptive TTL."""

    def __init__(self, redis_url: str):
        """Initialize Redis cache client.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        """
        self.redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._client is None:
            self._client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False,  # Handle bytes explicitly
            )
            logger.info("Redis cache connected", extra={"redis_url": self.redis_url})

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis cache disconnected")

    async def get(self, key: str) -> Optional[bytes]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value as bytes, or None if not found
        """
        if self._client is None:
            await self.connect()

        try:
            value = await self._client.get(key)
            if value:
                logger.debug("Cache hit", extra={"key": key})
                return value
            else:
                logger.debug("Cache miss", extra={"key": key})
                return None
        except Exception as e:
            logger.warning("Redis get failed", extra={"key": key, "error": str(e)})
            return None

    async def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: int,
    ) -> None:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (bytes)
            ttl_seconds: Time to live in seconds
        """
        if self._client is None:
            await self.connect()

        try:
            # Add jitter: ±10%
            jitter = random.uniform(0.9, 1.1)
            actual_ttl = int(ttl_seconds * jitter)

            await self._client.set(key, value, ex=actual_ttl)
            logger.debug(
                "Cache set",
                extra={"key": key, "ttl": actual_ttl, "size_bytes": len(value)},
            )
        except Exception as e:
            logger.warning("Redis set failed", extra={"key": key, "error": str(e)})

    async def get_json(self, key: str) -> Optional[Any]:
        """Get JSON value from cache.

        Args:
            key: Cache key

        Returns:
            Deserialized JSON value, or None
        """
        value_bytes = await self.get(key)
        if value_bytes:
            try:
                return json.loads(value_bytes.decode("utf-8"))
            except Exception as e:
                logger.warning("JSON decode failed", extra={"key": key, "error": str(e)})
                return None
        return None

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl_seconds: int,
    ) -> None:
        """Set JSON value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON-serialized)
            ttl_seconds: Time to live in seconds
        """
        try:
            value_bytes = json.dumps(value).encode("utf-8")
            await self.set(key, value_bytes, ttl_seconds)
        except Exception as e:
            logger.warning("JSON encode failed", extra={"key": key, "error": str(e)})

    async def get_or_set(
        self,
        key: str,
        factory_fn: Callable[[], Any],
        ttl_fn: Callable[[Any], int],
    ) -> Any:
        """Get from cache or compute and store.

        Args:
            key: Cache key
            factory_fn: Async function to compute value if cache miss
            ttl_fn: Function to compute TTL based on value

        Returns:
            Cached or computed value
        """
        # Try cache first
        cached = await self.get_json(key)
        if cached is not None:
            return cached

        # Cache miss — compute value
        try:
            value = await factory_fn() if callable(factory_fn) else factory_fn
            ttl = ttl_fn(value)
            await self.set_json(key, value, ttl)
            return value
        except Exception as e:
            logger.error(
                "Cache factory function failed",
                extra={"key": key, "error": str(e)},
            )
            raise

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern.

        Args:
            pattern: Redis key pattern (e.g., "econ:calendar:*")

        Returns:
            Number of keys deleted
        """
        if self._client is None:
            await self.connect()

        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self._client.delete(*keys)
                logger.info(
                    "Cache pattern invalidated",
                    extra={"pattern": pattern, "deleted": deleted},
                )
                return deleted
            else:
                return 0
        except Exception as e:
            logger.warning(
                "Pattern invalidation failed",
                extra={"pattern": pattern, "error": str(e)},
            )
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists
        """
        if self._client is None:
            await self.connect()

        try:
            return await self._client.exists(key) > 0
        except Exception:
            return False
