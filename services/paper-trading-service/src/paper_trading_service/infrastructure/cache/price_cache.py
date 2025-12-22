import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Awaitable, Callable, Final, Optional

from paper_trading_service.constants import CacheKeyPrefix
from paper_trading_service.constants import PRICE_CACHE_TTL_SECONDS
from paper_trading_service.infrastructure.cache.redis_client import RedisClient


logger = logging.getLogger(__name__)

# Type alias for a function that fetches prices.
# Callable[[str], Awaitable[Optional[Decimal]]] means:
#   - Callable[[str], ...] → a function that takes one string argument (symbol)
#   - Awaitable[...] → it's async (you can await it)
#   - Optional[Decimal] → returns Decimal or None
# This lets us accept any async function matching this signature in get_or_fetch().
PriceFetcher = Callable[[str], Awaitable[Optional[Decimal]]]

@dataclass(frozen=True)
class CachedPrice:
    """Immutable cached price."""
    symbol: str
    price: Decimal
    timestamp: datetime
    source: str
    
    def to_json(self) -> str:
        return json.dumps({
            "symbol": self.symbol,
            "price": str(self.price),  # Decimal → string for precision
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        })
    
    @classmethod
    def from_json(cls, json_str: Optional[str]) -> Optional["CachedPrice"]:
        if json_str is None:
            return None
        try:
            data = json.loads(json_str)
            return cls(
                symbol=data["symbol"],
                price=Decimal(data["price"]),
                timestamp=datetime.fromisoformat(data["timestamp"]),
                source=data["source"],
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None


class PriceCache:
    """Cache-aside implementation for market prices."""
    
    KEY_PREFIX: Final[str] = CacheKeyPrefix.PRICE
    
    def __init__(self, redis_client: RedisClient, ttl_seconds: int = PRICE_CACHE_TTL_SECONDS) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0
    
    def _make_key(self, symbol: str) -> str:
        return f"{self.KEY_PREFIX}{symbol}"
    
    async def get(self, symbol: str) -> Optional[CachedPrice]:
        try:
            json_str = await self._redis.get(self._make_key(symbol))
            if json_str is None:
                self._misses += 1
                return None
            price = CachedPrice.from_json(json_str)
            if price:
                self._hits += 1
            return price
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self._misses += 1
            return None
    
    async def set(self, price: CachedPrice) -> bool:
        try:
            await self._redis.set(
                key=self._make_key(price.symbol),
                value=price.to_json(),
                ttl=self._ttl,
            )
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def invalidate(self, symbol: str) -> bool:
        try:
            return await self._redis.delete(self._make_key(symbol))
        except Exception as e:
            logger.error(f"Cache invalidate error: {e}")
            return False
    
    async def get_or_fetch(self, symbol: str, fetch_fn: PriceFetcher) -> Optional[CachedPrice]:
        """Cache-aside: check cache first, fetch on miss, cache result."""
        cached = await self.get(symbol)
        if cached is not None:
            return cached
        
        try:
            price_value = await fetch_fn(symbol)
            if price_value is None:
                return None
            
            cached_price = CachedPrice(
                symbol=symbol,
                price=price_value,
                timestamp=datetime.now(timezone.utc),
                source="fetch",
            )
            await self.set(cached_price)
            return cached_price
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return None
    
    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {"hits": self._hits, "misses": self._misses, "hit_rate": f"{hit_rate:.0%}"}
