"""
Health checks for Kubernetes probes.

functools.lru_cache: Memoizes function results. Same arguments return cached result.
Use maxsize=1 for functions with no arguments (like get_version).
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Final, List, Optional

from paper_trading_service.constants import HEALTH_LATENCY_CRITICAL_MS
from paper_trading_service.constants import HEALTH_LATENCY_WARNING_MS
from paper_trading_service.infrastructure.cache.redis_client import RedisClient


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = {"name": self.name, "status": self.status.value}
        if self.latency_ms is not None:
            result["latency_ms"] = round(self.latency_ms, 2)
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class SystemHealth:
    status: HealthStatus
    components: List[ComponentHealth] = field(default_factory=list)
    version: Optional[str] = None
    uptime_seconds: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2) if self.uptime_seconds else None,
            "components": [c.to_dict() for c in self.components],
        }


class HealthChecker:
    """Health checker for Kubernetes liveness/readiness probes."""
    
    VERSION: Final[str] = "1.0.0"
    
    def __init__(self, redis_client: Optional[RedisClient] = None) -> None:
        self._redis = redis_client
        self._start_time = time.time()
    
    @lru_cache(maxsize=1)
    def get_version(self) -> str:
        return self.VERSION
    
    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time
    
    async def check_redis(self) -> ComponentHealth:
        if self._redis is None:
            return ComponentHealth(name="redis", status=HealthStatus.UNHEALTHY, error="Not configured")
        
        start = time.perf_counter()
        try:
            await self._redis.ping()
            latency_ms = (time.perf_counter() - start) * 1000
            
            if latency_ms < HEALTH_LATENCY_WARNING_MS:
                status = HealthStatus.HEALTHY
            elif latency_ms < HEALTH_LATENCY_CRITICAL_MS:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY
            
            return ComponentHealth(name="redis", status=status, latency_ms=latency_ms)
        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                error=str(e),
            )
    
    async def liveness(self) -> SystemHealth:
        """Liveness: minimal check, don't check dependencies."""
        return SystemHealth(
            status=HealthStatus.HEALTHY,
            version=self.get_version(),
            uptime_seconds=self.uptime_seconds,
        )
    
    async def readiness(self) -> SystemHealth:
        """Readiness: check all dependencies."""
        components = [await self.check_redis()]
        
        if any(c.status == HealthStatus.UNHEALTHY for c in components):
            status = HealthStatus.UNHEALTHY
        elif any(c.status == HealthStatus.DEGRADED for c in components):
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY
        
        return SystemHealth(
            status=status,
            components=components,
            version=self.get_version(),
            uptime_seconds=self.uptime_seconds,
        )