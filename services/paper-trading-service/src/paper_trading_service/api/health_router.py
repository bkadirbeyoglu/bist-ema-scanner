"""Health API endpoints for Kubernetes probes."""

from typing import Any, Dict
from fastapi import APIRouter, Response, status

from paper_trading_service.infrastructure.health.health_checker import HealthChecker
from paper_trading_service.infrastructure.health.health_checker import HealthStatus
from paper_trading_service.infrastructure.health.health_checker import SystemHealth
from paper_trading_service.infrastructure.cache.redis_client import get_global_redis_client

router = APIRouter(prefix="/health", tags=["health"])


def _get_checker() -> HealthChecker:
    """Get health checker with Redis client."""
    try:
        redis = get_global_redis_client()
        return HealthChecker(redis_client=redis)
    except RuntimeError:
        return HealthChecker()  # No Redis configured


def _respond(response: Response, health: SystemHealth) -> Dict[str, Any]:
    response.status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if health.status == HealthStatus.UNHEALTHY
        else status.HTTP_200_OK
    )
    return health.to_dict()


@router.get("/live")
async def liveness(response: Response) -> Dict[str, Any]:
    """Liveness probe - don't check dependencies."""
    return _respond(response, await _get_checker().liveness())


@router.get("/ready")
async def readiness(response: Response) -> Dict[str, Any]:
    """Readiness probe - check all dependencies."""
    return _respond(response, await _get_checker().readiness())