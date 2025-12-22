"""Tests for health checks."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from paper_trading_service.infrastructure.health.health_checker import HealthChecker
from paper_trading_service.infrastructure.health.health_checker import HealthStatus


class TestHealthChecker:
    
    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        client = MagicMock()
        client.ping = AsyncMock(return_value=True)
        return client
    
    @pytest.fixture
    def checker(self, mock_redis: MagicMock) -> HealthChecker:
        return HealthChecker(redis_client=mock_redis)
    
    async def test_liveness_always_healthy(self, checker: HealthChecker) -> None:
        result = await checker.liveness()
        assert result.status == HealthStatus.HEALTHY
    
    async def test_readiness_healthy_when_redis_up(self, checker: HealthChecker) -> None:
        result = await checker.readiness()
        assert result.status == HealthStatus.HEALTHY
    
    async def test_readiness_unhealthy_when_redis_down(self, checker: HealthChecker, mock_redis: MagicMock) -> None:
        mock_redis.ping = AsyncMock(side_effect=Exception("Connection refused"))
        
        result = await checker.readiness()
        
        assert result.status == HealthStatus.UNHEALTHY