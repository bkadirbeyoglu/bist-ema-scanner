"""
Application constants.

typing.Final (Python 3.8+): Indicates a variable should not be reassigned.
Type checkers (mypy/pyright) enforce this. Runtime reassignment is still
possible—Final is for static analysis and documentation.
"""

from typing import Final

# Redis
REDIS_HOST: Final[str] = "localhost"
REDIS_PORT: Final[int] = 6379
REDIS_DB: Final[int] = 0
REDIS_MAX_CONNECTIONS: Final[int] = 10

# Cache TTL (seconds)
PRICE_CACHE_TTL_SECONDS: Final[int] = 10

# Rate limiting
RATE_LIMIT_REQUESTS_PER_MINUTE: Final[int] = 60
RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60

# Health thresholds (milliseconds)
HEALTH_LATENCY_WARNING_MS: Final[int] = 100
HEALTH_LATENCY_CRITICAL_MS: Final[int] = 500


class CacheKeyPrefix:
    """Key prefixes for organization (enables KEYS "price:*")."""
    PRICE: Final[str] = "price:"
    RATE_LIMIT: Final[str] = "rate:"