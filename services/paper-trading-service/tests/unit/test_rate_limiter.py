"""Tests for sliding window rate limiter."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from paper_trading_service.infrastructure.cache.rate_limiter import RateLimiter
from paper_trading_service.infrastructure.cache.rate_limiter import RateLimitResult


class TestRateLimiter:
    
    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        client = MagicMock()
        client.zadd = AsyncMock(return_value=1)
        client.zcount = AsyncMock(return_value=0)
        client.zremrangebyscore = AsyncMock(return_value=0)
        client.expire = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=True)
        return client
    
    @pytest.fixture
    def limiter(self, mock_redis: MagicMock) -> RateLimiter:
        return RateLimiter(redis_client=mock_redis, max_requests=10, window_seconds=60)
    
    async def test_first_request_allowed(self, limiter: RateLimiter, mock_redis: MagicMock) -> None:
        result = await limiter.check("user123")
        
        assert result.allowed is True
        assert result.remaining == 9
    
    async def test_at_limit_denied(self, limiter: RateLimiter, mock_redis: MagicMock) -> None:
        mock_redis.zcount = AsyncMock(return_value=10)  # At limit
        
        result = await limiter.check("user123")
        
        assert result.allowed is False
        assert result.remaining == 0
    
    async def test_different_users_independent(self, limiter: RateLimiter, mock_redis: MagicMock) -> None:
        keys_checked: list[str] = []
        
        async def track(key: str, min_s: float, max_s: float) -> int:
            keys_checked.append(key)
            return 0
        
        mock_redis.zcount = AsyncMock(side_effect=track)
        
        await limiter.check("user1")
        await limiter.check("user2")
        
        assert "rate:user1" in keys_checked
        assert "rate:user2" in keys_checked