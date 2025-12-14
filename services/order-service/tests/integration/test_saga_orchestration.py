"""
Integration Tests for Saga Orchestration.

Tests the full saga lifecycle with the orchestrator.
"""

import pytest
from decimal import Decimal

from order_service.domain.entities import Order, OrderSide, OrderType
from order_service.domain.saga_state import SagaState
from order_service.application.saga_orchestrator import SagaOrchestrator


@pytest.fixture
def orchestrator() -> SagaOrchestrator:
    """Create fresh orchestrator for each test."""
    return SagaOrchestrator()


class TestSagaOrchestrator:
    """Test suite for SagaOrchestrator."""
    
    @pytest.mark.asyncio
    async def test_start_and_complete_saga(
        self, 
        orchestrator: SagaOrchestrator,
        sample_order: Order
    ):
        """Test starting and completing a saga."""
        execution = await orchestrator.start_order_saga(sample_order)
        
        assert execution.state == SagaState.COMPLETED
        assert len(execution.completed_steps) == 5
    
    @pytest.mark.asyncio
    async def test_saga_status_tracking(
        self,
        orchestrator: SagaOrchestrator,
        sample_order: Order
    ):
        """Test saga status can be queried."""
        await orchestrator.start_order_saga(sample_order)
        
        execution = await orchestrator.get_saga_status(sample_order.id)
        
        assert execution is not None
        assert execution.saga_id == sample_order.id
        assert execution.state == SagaState.COMPLETED
    
    @pytest.mark.asyncio
    async def test_cannot_start_duplicate_saga(
        self,
        orchestrator: SagaOrchestrator,
        sample_order: Order
    ):
        """Test that duplicate sagas are rejected."""
        await orchestrator.start_order_saga(sample_order)
        
        with pytest.raises(ValueError, match="already exists"):
            await orchestrator.start_order_saga(sample_order)
    
    @pytest.mark.asyncio
    async def test_completion_callback(
        self,
        orchestrator: SagaOrchestrator,
        sample_order: Order
    ):
        """Test completion callbacks are triggered."""
        callback_called = False
        
        async def on_complete(order: Order, execution) -> None:
            nonlocal callback_called
            callback_called = True
        
        orchestrator.on_complete(on_complete)
        await orchestrator.start_order_saga(sample_order)
        
        assert callback_called
    
    @pytest.mark.asyncio
    async def test_failure_callback(
        self,
        orchestrator: SagaOrchestrator,
        large_order: Order
    ):
        """Test failure callbacks are triggered."""
        callback_called = False
        
        async def on_failed(order: Order, execution) -> None:
            nonlocal callback_called
            callback_called = True
        
        orchestrator.on_failed(on_failed)
        await orchestrator.start_order_saga(large_order)
        
        assert callback_called
    
    @pytest.mark.asyncio
    async def test_orchestrator_stats(self, orchestrator: SagaOrchestrator):
        """Test orchestrator statistics."""
        orders = [
            Order(
                id=f"order-{i}",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("100"),
                account_id="account-001"
            )
            for i in range(3)
        ]
        
        for order in orders:
            await orchestrator.start_order_saga(order)
        
        stats = orchestrator.stats()
        
        assert stats["total_sagas"] == 3
        assert stats["by_state"]["COMPLETED"] == 3