"""
Async Redis client with connection pooling.

asynccontextmanager (Python 3.7+): Converts an async generator into a context manager.
Code before yield runs on entry, code after yield runs on exit (cleanup).
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from paper_trading_service.constants import REDIS_DB
from paper_trading_service.constants import REDIS_HOST
from paper_trading_service.constants import REDIS_MAX_CONNECTIONS
from paper_trading_service.constants import REDIS_PORT

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client with connection pooling (reuses connections for performance)."""
    
    def __init__(
        self,
        host: str = REDIS_HOST,
        port: int = REDIS_PORT,
        db: int = REDIS_DB,
        max_connections: int = REDIS_MAX_CONNECTIONS,
    ) -> None:
        self._host = host
        self._port = port
        self._db = db
        self._max_connections = max_connections
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[aioredis.Redis] = None
        self._connected = False
    
    async def connect(self) -> None:
        if self._connected:
            return
        self._pool = ConnectionPool(
            host=self._host,
            port=self._port,
            db=self._db,
            max_connections=self._max_connections,
            decode_responses=True,
        )
        self._redis = aioredis.Redis(connection_pool=self._pool)
        await self._redis.ping()
        self._connected = True
        logger.info(f"Connected to Redis at {self._host}:{self._port}")
    
    async def disconnect(self) -> None:
        if not self._connected:
            return
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    async def ping(self) -> bool:
        if not self._redis:
            return False
        try:
            return await self._redis.ping() is True
        except Exception:
            return False
    
    # String operations - simple key-value storage
    async def get(self, key: str) -> Optional[str]:
        """GET key - retrieve value by key, returns None if not found."""
        if not self._redis:
            raise RuntimeError("Not connected")
        return await self._redis.get(key)
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """SET key value - store value. SETEX key ttl value - store with expiration."""
        if not self._redis:
            raise RuntimeError("Not connected")
        if ttl:
            await self._redis.setex(key, ttl, value)  # Expires after ttl seconds
        else:
            await self._redis.set(key, value)
        return True
    
    async def delete(self, key: str) -> bool:
        """DEL key - remove key from Redis."""
        if not self._redis:
            raise RuntimeError("Not connected")
        return await self._redis.delete(key) > 0
    
    # Sorted set operations - members with scores, auto-sorted by score
    async def zadd(self, name: str, mapping: dict[str, float]) -> int:
        """ZADD key score member - add member with score (we use timestamp as score)."""
        if not self._redis:
            raise RuntimeError("Not connected")
        return await self._redis.zadd(name, mapping)  # type: ignore
    
    async def zcount(self, name: str, min_score: float, max_score: float) -> int:
        """ZCOUNT key min max - count members with scores in range."""
        if not self._redis:
            raise RuntimeError("Not connected")
        return await self._redis.zcount(name, min_score, max_score)
    
    async def zremrangebyscore(self, name: str, min_score: float, max_score: float) -> int:
        """ZREMRANGEBYSCORE key min max - remove members with scores in range."""
        if not self._redis:
            raise RuntimeError("Not connected")
        return await self._redis.zremrangebyscore(name, min_score, max_score)
    
    async def expire(self, name: str, seconds: int) -> bool:
        if not self._redis:
            raise RuntimeError("Not connected")
        return await self._redis.expire(name, seconds)


@asynccontextmanager
async def get_redis_client(
    host: str = REDIS_HOST,
    port: int = REDIS_PORT,
    db: int = REDIS_DB,
) -> AsyncIterator[RedisClient]:
    """
    Context manager for Redis lifecycle.
    
    Usage:
        async with get_redis_client() as client:
            await client.set("key", "value")
        # Automatically disconnected when block exits
    
    Why use a generator with 'yield' instead of a regular function with 'return'?
    
        A regular function ends when it returns - no cleanup possible:
        
            async def create_client() -> RedisClient:
                client = RedisClient()
                await client.connect()
                return client  # Function ends here, who calls disconnect?
        
        A generator pauses at 'yield' and resumes after the caller is done:
        
            async def get_redis_client() -> AsyncIterator[RedisClient]:
                await client.connect()      # 1. Setup
                yield client                # 2. Pause - caller uses client
                await client.disconnect()   # 3. Cleanup - runs after caller is done
        
        This "setup → pause → cleanup" pattern is perfect for resource management.
        The @asynccontextmanager decorator transforms it into 'async with' syntax.
    
    Why AsyncIterator[RedisClient] instead of RedisClient?
    
        Any function using 'yield' must declare an iterator return type - that's
        how Python's type system works. In this code, we're not actually iterating
        over anything; we yield only once. We use 'yield' purely for its
        "pause and resume" behavior.
    """
    client = RedisClient(host=host, port=port, db=db)
    await client.connect()  # 1. Setup
    try:
        yield client  # 2. Pause - provides client to 'async with' block
    finally:
        await client.disconnect()  # 3. Cleanup - runs even if exception occurs


# Global client for application-wide use (e.g., FastAPI lifespan)
# Use get_redis_client() context manager for scripts and tests.
# Use global client for long-running applications where one connection serves all requests.
_global_client: Optional[RedisClient] = None


async def init_global_redis_client(
    host: str = REDIS_HOST,
    port: int = REDIS_PORT,
    db: int = REDIS_DB,
) -> RedisClient:
    """Initialize the global Redis client. Call once at application startup."""
    global _global_client
    if _global_client is None:
        _global_client = RedisClient(host=host, port=port, db=db)
        await _global_client.connect()
    return _global_client


def get_global_redis_client() -> RedisClient:
    """Get the global Redis client. Raises if not initialized."""
    if _global_client is None:
        raise RuntimeError("Global Redis client not initialized. Call init_global_redis_client() first.")
    return _global_client


async def close_global_redis_client() -> None:
    """Close the global Redis client. Call at application shutdown."""
    global _global_client
    if _global_client is not None:
        await _global_client.disconnect()
        _global_client = None