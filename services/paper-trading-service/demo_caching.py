"""Demo: docker compose up redis -d && poetry run python demo_caching.py"""

import asyncio
import random
from datetime import datetime
from decimal import Decimal

from paper_trading_service.infrastructure.cache.price_cache import PriceCache
from paper_trading_service.infrastructure.cache.rate_limiter import RateLimiter
from paper_trading_service.infrastructure.cache.redis_client import get_redis_client
from paper_trading_service.infrastructure.health.health_checker import HealthChecker


async def main():
    print("Redis Caching Demo\n" + "=" * 40)
    
    async with get_redis_client() as redis:
        # Price cache demo
        cache = PriceCache(redis)
        
        async def mock_api(symbol: str) -> Decimal:
            await asyncio.sleep(0.1)  # 100ms API call
            return Decimal(str(random.uniform(100, 200)))
        
        start = datetime.now()
        price = await cache.get_or_fetch("AAPL", mock_api)
        ms1 = (datetime.now() - start).total_seconds() * 1000
        
        start = datetime.now()
        price = await cache.get_or_fetch("AAPL", mock_api)
        ms2 = (datetime.now() - start).total_seconds() * 1000
        
        print(f"Cache MISS: {ms1:.0f}ms | Cache HIT: {ms2:.0f}ms")
        print(f"Stats: {cache.stats}")
        
        # Rate limiter demo
        limiter = RateLimiter(redis, max_requests=5, window_seconds=10)
        user = f"user_{random.randint(1000, 9999)}"
        
        print(f"\nRate limiting (5 req/10s):")
        for i in range(7):
            r = await limiter.check(user)
            print(f"  Request {i+1}: {'✓' if r.allowed else '✗'} (remaining: {r.remaining})")
        await limiter.reset(user)
        
        # Health check demo
        checker = HealthChecker(redis_client=redis)
        ready = await checker.readiness()
        print(f"\nReadiness: {ready.status.value}")


if __name__ == "__main__":
    asyncio.run(main())