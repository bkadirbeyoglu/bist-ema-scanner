# tests/integration/contexts/test_cross_context_integration.py
"""
Integration tests across bounded contexts.

These tests verify that contexts can communicate correctly through events.
They use REAL implementations (not mocks) to catch integration bugs.
"""

import pytest
import asyncio
from decimal import Decimal
from typing import List

from trading_system.contexts.composition_root import ApplicationContext
from trading_system.contexts.order_management.domain.entities.order import (
    OrderSide, OrderType
)
from trading_system.shared_kernel.events import BaseEvent

@pytest.fixture
async def app_context():
    """
    Fixture providing application context.
    
    This fixture:
    1. Creates a fresh ApplicationContext for each test
    2. Yields it to the test
    3. Cleans up after test completes
    """
    context = ApplicationContext()
    yield context
    await context.shutdown()

@pytest.mark.asyncio
class TestCrossContextIntegration:
    """Test event-driven integration between contexts."""
    
    async def test_order_creation_triggers_risk_check(self, app_context):
        """
        Test workflow: Order Created → Risk Check → Risk Approved
        
        This test verifies the HAPPY PATH:
        1. Order Management creates an order
        2. OrderCreatedEvent is published
        3. Risk Management receives the event
        4. Risk checks pass
        5. RiskCheckPassedEvent is published
        """
        order_service = app_context.get_order_service()
        
        # Event spy - captures events for verification
        events_received: List[BaseEvent] = []
        
        async def event_spy(event: BaseEvent):
            """Capture all published events."""
            events_received.append(event)
        
        # Subscribe spy to relevant events
        from trading_system.contexts.order_management.domain.events import (
            OrderCreatedEvent
        )
        from trading_system.contexts.risk_management.domain.events import (
            RiskCheckPassedEvent
        )
        
        app_context.event_bus.subscribe(OrderCreatedEvent, event_spy)
        app_context.event_bus.subscribe(RiskCheckPassedEvent, event_spy)
        
        # ACT: Create order with SMALL notional value (under $10,000 limit)
        # Changed from quantity=100, price=150 ($15,000) 
        # To quantity=50, price=100 ($5,000) - PASSES risk check
        order = await order_service.create_order(
            symbol="AAPL",
            quantity=Decimal("50"),  # Changed from 100
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("100.00")  # Changed from 150.00
        )
        
        # Give event bus time to process
        await asyncio.sleep(0.1)
        
        # ASSERT: Verify event flow
        assert len(events_received) >= 2, (
            f"Expected at least 2 events, got {len(events_received)}. "
            f"Events received: {[type(e).__name__ for e in events_received]}"
        )
        
        # Find OrderCreatedEvent
        order_created_events = [
            e for e in events_received 
            if isinstance(e, OrderCreatedEvent)
        ]
        assert len(order_created_events) == 1
        assert order_created_events[0].order_id == str(order.id)
        
        # Find RiskCheckPassedEvent
        risk_passed_events = [
            e for e in events_received 
            if isinstance(e, RiskCheckPassedEvent)
        ]
        assert len(risk_passed_events) == 1
        assert risk_passed_events[0].order_id == str(order.id)
    
    async def test_large_order_triggers_risk_breach(self, app_context):
        """
        Test workflow: Large Order → Risk Check → Risk Breach
        
        This test verifies the ERROR PATH:
        1. Order created with large notional value
        2. Risk Management detects limit breach
        3. RiskLimitBreachedEvent is published
        """
        order_service = app_context.get_order_service()
        
        events_received: List[BaseEvent] = []
        
        async def event_spy(event: BaseEvent):
            events_received.append(event)
        
        from trading_system.contexts.risk_management.domain.events import (
            RiskLimitBreachedEvent
        )
        app_context.event_bus.subscribe(RiskLimitBreachedEvent, event_spy)
        
        # ACT: Create large order (should breach risk limits)
        # Notional value = 1000 shares × $500 = $500,000
        # Risk limit = $10,000
        order = await order_service.create_order(
            symbol="AAPL",
            quantity=Decimal("1000"),
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("500.00")
        )
        
        await asyncio.sleep(0.1)
        
        # ASSERT: Verify breach event
        breach_events = [
            e for e in events_received 
            if isinstance(e, RiskLimitBreachedEvent)
        ]
        
        assert len(breach_events) == 1
        breach = breach_events[0]
        assert breach.limit_type == "order_size"
        assert breach.severity == "critical"
        assert "order_id" in breach.details
    
    async def test_multiple_contexts_react_to_same_event(self, app_context):
        """
        Test that multiple contexts can subscribe to same event.
        
        Event Fan-Out Pattern:
        ---------------------
        One event → Multiple subscribers
        
                   OrderCreatedEvent
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          ▼
           Risk    Portfolio    Audit
        """
        order_service = app_context.get_order_service()
        
        # Track which handlers executed
        handler_calls = {
            "risk": False,
            "portfolio": False,
            "audit": False
        }
        
        from trading_system.contexts.order_management.domain.events import (
            OrderCreatedEvent
        )
        
        # Register multiple handlers for same event
        async def risk_handler(event: OrderCreatedEvent):
            handler_calls["risk"] = True
        
        async def portfolio_handler(event: OrderCreatedEvent):
            handler_calls["portfolio"] = True
        
        async def audit_handler(event: OrderCreatedEvent):
            handler_calls["audit"] = True
        
        app_context.event_bus.subscribe(OrderCreatedEvent, risk_handler)
        app_context.event_bus.subscribe(OrderCreatedEvent, portfolio_handler)
        app_context.event_bus.subscribe(OrderCreatedEvent, audit_handler)
        
        # ACT: Create order
        await order_service.create_order(
            symbol="MSFT",
            quantity=Decimal("50"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET
        )
        
        await asyncio.sleep(0.1)
        
        # ASSERT: All handlers should have executed
        assert handler_calls["risk"], "Risk handler should execute"
        assert handler_calls["portfolio"], "Portfolio handler should execute"
        assert handler_calls["audit"], "Audit handler should execute"