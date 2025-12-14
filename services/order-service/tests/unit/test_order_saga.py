"""
Unit Tests for Order Placement Saga.

Tests saga execution, step order, and compensation logic.
"""

import pytest
from decimal import Decimal

# Domain imports
from order_service.domain.entities import Order, OrderSide, OrderType, OrderStatus
from order_service.domain.saga_state import SagaState

# Application imports
from order_service.application.order_saga import OrderPlacementSaga


class TestOrderPlacementSaga:
    """Test suite for OrderPlacementSaga."""
    
    @pytest.mark.asyncio
    async def test_saga_defines_correct_steps(self, sample_order: Order):
        """Verify saga has all required steps in correct order."""
        saga = OrderPlacementSaga(sample_order)
        
        step_names = [step.name for step in saga.steps]
        
        expected = [
            "validate_order",
            "get_market_price",
            "check_risk_limits",
            "reserve_funds",
            "submit_order"
        ]
        
        assert step_names == expected
    
    @pytest.mark.asyncio
    async def test_saga_initial_context(self, sample_order: Order):
        """Verify initial context contains order data."""
        saga = OrderPlacementSaga(sample_order)
        context = saga.build_initial_context()
        
        assert context["order_id"] == "test-order-001"
        assert context["symbol"] == "AAPL"
        assert context["side"] == "BUY"
        assert context["quantity"] == "100"
        assert context["current_price"] is None
        assert context["reserved_funds"] is None
    
    @pytest.mark.asyncio
    async def test_saga_completes_successfully(self, sample_order: Order):
        """Test full saga execution succeeds."""
        saga = OrderPlacementSaga(sample_order)
        
        execution = await saga.execute()
        
        assert execution.state == SagaState.COMPLETED
        assert len(execution.completed_steps) == 5
        assert sample_order.status == OrderStatus.FILLED
        assert sample_order.filled_quantity == sample_order.quantity
    
    @pytest.mark.asyncio
    async def test_saga_compensates_on_failure(self, large_order: Order):
        """Test saga runs compensation when step fails."""
        saga = OrderPlacementSaga(large_order)
        execution = await saga.execute()
        
        assert execution.state == SagaState.COMPENSATED
        assert execution.failed_step == "check_risk_limits"
        assert "exceeds limit" in execution.error_message
    
    @pytest.mark.asyncio
    async def test_saga_tracks_completed_steps_before_failure(
        self, 
        large_order: Order
    ):
        """Test saga records which steps completed before failure."""
        saga = OrderPlacementSaga(large_order)
        execution = await saga.execute()
        
        # Should complete validation and price before failing at risk
        assert "validate_order" in execution.completed_steps
        assert "get_market_price" in execution.completed_steps
        assert "check_risk_limits" not in execution.completed_steps


class TestOrderValidation:
    """Test order validation logic."""
    
    @pytest.mark.asyncio
    async def test_rejects_empty_symbol(self, sample_order: Order):
        """Empty symbol should be rejected."""
        sample_order.symbol = ""
        
        saga = OrderPlacementSaga(sample_order)
        context = saga.build_initial_context()
        context["symbol"] = ""
        
        with pytest.raises(ValueError, match="Invalid symbol"):
            await saga.steps[0].forward(context)
    
    @pytest.mark.asyncio
    async def test_rejects_negative_quantity(self, sample_order: Order):
        """Negative quantity should be rejected."""
        sample_order.quantity = Decimal("-100")
        
        saga = OrderPlacementSaga(sample_order)
        context = saga.build_initial_context()
        context["quantity"] = "-100"
        
        with pytest.raises(ValueError, match="must be positive"):
            await saga.steps[0].forward(context)
    
    @pytest.mark.asyncio
    async def test_rejects_limit_order_without_price(self, sample_order: Order):
        """Limit order without limit_price should be rejected."""
        sample_order.order_type = OrderType.LIMIT
        sample_order.limit_price = None
        
        saga = OrderPlacementSaga(sample_order)
        context = saga.build_initial_context()
        context["order_type"] = "LIMIT"
        context["limit_price"] = None
        
        with pytest.raises(ValueError, match="requires limit_price"):
            await saga.steps[0].forward(context)


class TestContextFlow:
    """Test context flows correctly through saga steps."""
    
    @pytest.mark.asyncio
    async def test_price_step_adds_to_context(self, sample_order: Order):
        """Price step should add current_price and estimated_value."""
        saga = OrderPlacementSaga(sample_order)
        context = saga.build_initial_context()
        
        # Run validation first
        context = await saga.steps[0].forward(context)
        
        # Run price step
        context = await saga.steps[1].forward(context)
        
        assert context["current_price"] is not None
        assert context["estimated_value"] is not None
        assert Decimal(context["estimated_value"]) > 0
    
    @pytest.mark.asyncio
    async def test_reserve_funds_includes_buffer(self, sample_order: Order):
        """Reserved funds should be > estimated value (includes buffer)."""
        saga = OrderPlacementSaga(sample_order)
        context = saga.build_initial_context()
        
        # Run through to reserve_funds
        for i in range(4):
            context = await saga.steps[i].forward(context)
        
        reserved = Decimal(context["reserved_funds"])
        estimated = Decimal(context["estimated_value"])
        
        # Reserved should be > estimated (2% buffer)
        assert reserved > estimated