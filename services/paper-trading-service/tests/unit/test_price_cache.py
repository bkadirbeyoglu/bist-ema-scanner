"""Tests for price caching."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from paper_trading_service.infrastructure.cache.price_cache import CachedPrice
from paper_trading_service.infrastructure.cache.price_cache import PriceCache


class TestCachedPrice:
    
    def test_json_round_trip(self) -> None:
        original = CachedPrice(
            symbol="AAPL",
            price=Decimal("150.25"),
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            source="api",
        )
        restored = CachedPrice.from_json(original.to_json())
        
        assert restored is not None
        assert restored.symbol == original.symbol
        assert restored.price == original.price
    
    def test_from_json_handles_invalid(self) -> None:
        assert CachedPrice.from_json(None) is None
        assert CachedPrice.from_json("invalid") is None


class TestPriceCache:
    
    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        client = MagicMock()
        client.get = AsyncMock(return_value=None)
        client.set = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=True)
        return client
    
    @pytest.fixture
    def cache(self, mock_redis: MagicMock) -> PriceCache:
        return PriceCache(redis_client=mock_redis)
    
    async def test_cache_miss(self, cache: PriceCache) -> None:
        result = await cache.get("AAPL")
        assert result is None
    
    async def test_cache_hit(self, cache: PriceCache, mock_redis: MagicMock) -> None:
        cached = CachedPrice(
            symbol="AAPL",
            price=Decimal("150.25"),
            timestamp=datetime.now(timezone.utc),
            source="test",
        )
        mock_redis.get = AsyncMock(return_value=cached.to_json())
        
        result = await cache.get("AAPL")
        
        assert result is not None
        assert result.price == Decimal("150.25")
    
    async def test_get_or_fetch_uses_cache(self, cache: PriceCache, mock_redis: MagicMock) -> None:
        cached = CachedPrice(
            symbol="AAPL",
            price=Decimal("150.25"),
            timestamp=datetime.now(timezone.utc),
            source="cache",
        )
        mock_redis.get = AsyncMock(return_value=cached.to_json())
        
        fetch_called = False
        async def mock_fetch(symbol: str) -> Optional[Decimal]:
            nonlocal fetch_called
            fetch_called = True
            return Decimal("999.99")
        
        result = await cache.get_or_fetch("AAPL", mock_fetch)
        
        assert result.price == Decimal("150.25")
        assert fetch_called is False  # Didn't call fetch
    
    async def test_get_or_fetch_calls_fetch_on_miss(self, cache: PriceCache, mock_redis: MagicMock) -> None:
        async def mock_fetch(symbol: str) -> Optional[Decimal]:
            return Decimal("150.25")
        
        result = await cache.get_or_fetch("AAPL", mock_fetch)
        
        assert result.price == Decimal("150.25")
        mock_redis.set.assert_called_once()  # Cached the result