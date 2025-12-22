"""Sliding window rate limiter using Redis sorted sets (see Part 1 diagram)."""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Final

from paper_trading_service.constants import CacheKeyPrefix
from paper_trading_service.constants import RATE_LIMIT_REQUESTS_PER_MINUTE
from paper_trading_service.constants import RATE_LIMIT_WINDOW_SECONDS
from paper_trading_service.infrastructure.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    """Result with metadata for HTTP headers (X-RateLimit-Remaining, etc.)."""
    allowed: bool
    remaining: int
    reset_after_seconds: float


class RateLimiter:
    """Sliding window rate limiter."""
    
    KEY_PREFIX: Final[str] = CacheKeyPrefix.RATE_LIMIT
    
    def __init__(
        self,
        redis_client: RedisClient,
        max_requests: int = RATE_LIMIT_REQUESTS_PER_MINUTE,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._window_ms = window_seconds * 1000
    
    @property
    def max_requests(self) -> int:
        return self._max_requests
    
    def _make_key(self, identifier: str) -> str:
        return f"{self.KEY_PREFIX}{identifier}"
    
    async def check(self, identifier: str) -> RateLimitResult:
        """Check limit and record request if allowed."""
        key = self._make_key(identifier)
        now_ms = time.time() * 1000
        window_start_ms = now_ms - self._window_ms
        
        try:
            # Cleanup old entries
            await self._redis.zremrangebyscore(key, 0, window_start_ms)
            
            # Count current
            count = await self._redis.zcount(key, window_start_ms, now_ms)
            
            if count >= self._max_requests:
                return RateLimitResult(allowed=False, remaining=0, reset_after_seconds=self._window_seconds)
            
            # Record request
            await self._redis.zadd(key, {str(uuid.uuid4()): now_ms})
            await self._redis.expire(key, self._window_seconds + 60)
            
            return RateLimitResult(
                allowed=True,
                remaining=max(0, self._max_requests - count - 1),
                reset_after_seconds=self._window_seconds,
            )
        except Exception as e:
            logger.error(f"Rate limit error: {e}")
            return RateLimitResult(allowed=True, remaining=self._max_requests, reset_after_seconds=0)
    
    async def reset(self, identifier: str) -> bool:
        try:
            await self._redis.delete(self._make_key(identifier))
            return True
        except Exception:
            return False