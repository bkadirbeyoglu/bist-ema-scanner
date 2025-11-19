"""
Test file for Event Bus - Following TDD principles.

This demonstrates several Python testing concepts:
1. pytest fixtures - reusable test setup
2. async testing with pytest-asyncio
3. mocking with unittest.mock
4. property-based testing with Hypothesis

IMPORTANT: These tests are written BEFORE the implementation!
In TDD, we write failing tests first, then implement to make them pass.
"""

import asyncio
import uuid
from decimal import Decimal
from datetime import datetime
from typing import List, Any
from unittest.mock import AsyncMock, Mock, patch, call
import pytest
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import decimals, integers, text

# These imports will fail initially - that's TDD!
# We'll implement these classes after writing tests
from trading_system.shared_kernel.base_event import BaseEvent, DomainEvent
from trading_system.shared_kernel.event_bus import InMemoryEventBus
from trading_system.contexts.order_management.domain.events import (
    OrderCreatedEvent,
    OrderValidatedEvent,
    OrderRejectedEvent,
    OrderType,
    OrderSide
)


# ============================================
# FIXTURES - Reusable test components
# ============================================

@pytest.fixture  # This decorator marks a function as a fixture
def event_bus():
    """
    Pytest fixture - a function that provides test data/objects.
    
    Fixtures are pytest's dependency injection system:
    - Automatically called before tests that request them
    - Can perform setup and teardown
    - Promote test isolation (each test gets fresh instance)
    - Reduce code duplication
    
    The 'yield' keyword makes this a generator fixture:
    - Code before yield = setup (runs before test)
    - yield value = what the test receives
    - Code after yield = teardown (runs after test)
    
    Compare to traditional xUnit style:
    def setUp(self):  # Runs before each test
        self.bus = InMemoryEventBus()
    def tearDown(self):  # Runs after each test
        self.bus.clear()
    
    Fixtures are more flexible - can be composed and parameterized
    """
    bus = InMemoryEventBus()
    yield bus  # Test receives this value
    # Cleanup after test completes (even if test fails)
    bus.clear()


@pytest.fixture
def sample_order_event():
    """
    Fixture providing sample test data.
    
    Benefits of data fixtures:
    1. Consistent test data across tests
    2. Single place to update if data structure changes
    3. Can be parameterized for different scenarios
    4. Reduces test boilerplate
    """
    # Must provide all fields including those from BaseEvent
    return OrderCreatedEvent(
        # BaseEvent fields
        event_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        version=1,
        # OrderCreatedEvent fields
        order_id="TEST-001",
        symbol="AAPL",
        quantity=Decimal("100"),
        price=Decimal("150.50"),
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        account_id=None,
        metadata={}
    )


# ============================================
# BASIC UNIT TESTS
# ============================================

class TestInMemoryEventBus:
    """
    Test class for EventBus functionality.
    
    Classes in pytest:
    - Pure organization - not required (could use module-level functions)
    - No inheritance needed (unlike unittest.TestCase)
    - Methods are just regular functions
    - setUp/tearDown handled by fixtures
    
    Naming conventions:
    - Test classes start with Test
    - Test methods start with test_
    - This allows pytest to auto-discover tests
    """
    
    @pytest.mark.asyncio  # Tells pytest this is an async test
    async def test_subscribe_and_publish_single_handler(self, event_bus):
        """
        Test that a single handler receives published events.
        
        @pytest.mark.asyncio:
        - Marks async test functions
        - pytest will run with asyncio event loop
        - Without this, async tests won't work
        
        The AAA Pattern (Arrange-Act-Assert):
        - Arrange: Set up test data and conditions
        - Act: Execute the behavior being tested
        - Assert: Verify the outcome
        
        This pattern makes tests easy to read and understand
        """
        # === ARRANGE ===
        # AsyncMock is specifically for mocking async functions
        # Regular Mock won't work with await statements
        handler = AsyncMock()
        
        # Subscribe handler to specific event type
        # We're testing: "Does the handler get called when event is published?"
        event_bus.subscribe(OrderCreatedEvent, handler)
        
        # Create test event with all required fields
        event = OrderCreatedEvent(
            # BaseEvent fields
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            # OrderCreatedEvent fields
            order_id="123",
            symbol="AAPL",
            quantity=Decimal("100"),
            price=Decimal("150.50"),
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            account_id=None,
            metadata={}
        )
        
        # === ACT ===
        # Publish event - should trigger handler
        await event_bus.publish(event)
        
        # === ASSERT ===
        # Verify handler was called exactly once with our event
        handler.assert_called_once_with(event)
        # This checks both:
        # 1. Handler was called exactly once
        # 2. Handler received the correct event object
    
    @pytest.mark.asyncio
    async def test_multiple_handlers_receive_same_event(self, event_bus, sample_order_event):
        """
        Test that multiple handlers can subscribe to the same event type.
        
        This tests the publish-subscribe pattern:
        - Multiple subscribers to same event (one-to-many)
        - All handlers should receive the event
        - Order of handler execution doesn't matter
        
        Note: event_bus and sample_order_event are fixtures (auto-injected)
        """
        # === ARRANGE ===
        # Create three distinct handlers with names for debugging
        handler1 = AsyncMock(name="handler1")
        handler2 = AsyncMock(name="handler2")
        handler3 = AsyncMock(name="handler3")
        
        # All subscribe to same event type
        # This simulates multiple services interested in order creation
        event_bus.subscribe(OrderCreatedEvent, handler1)
        event_bus.subscribe(OrderCreatedEvent, handler2)
        event_bus.subscribe(OrderCreatedEvent, handler3)
        
        # === ACT ===
        await event_bus.publish(sample_order_event)
        
        # === ASSERT ===
        # Each handler should be called once with the same event
        handler1.assert_called_once_with(sample_order_event)
        handler2.assert_called_once_with(sample_order_event)
        handler3.assert_called_once_with(sample_order_event)
    
    @pytest.mark.asyncio
    async def test_handler_only_receives_subscribed_events(self, event_bus):
        """
        Test that handlers only receive events they subscribed to.
        
        This ensures:
        - Event routing works correctly
        - No handler receives unwanted events
        - Different event types are properly segregated
        """
        # === ARRANGE ===
        order_handler = AsyncMock(name="order_handler")
        validation_handler = AsyncMock(name="validation_handler")
        
        # Subscribe to different event types
        event_bus.subscribe(OrderCreatedEvent, order_handler)
        event_bus.subscribe(OrderValidatedEvent, validation_handler)
        
        # Create different event types with all required fields
        order_event = OrderCreatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            order_id="123",
            symbol="AAPL",
            quantity=Decimal("100"),
            price=Decimal("150.50"),
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            account_id=None,
            metadata={}
        )
        
        validation_event = OrderValidatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            order_id="123",
            validation_status="PASSED",
            validation_messages=[]
        )
        
        # === ACT ===
        await event_bus.publish(order_event)
        await event_bus.publish(validation_event)
        
        # === ASSERT ===
        # Each handler only called with its event type
        order_handler.assert_called_once_with(order_event)
        validation_handler.assert_called_once_with(validation_event)
        
        # Double-check call counts
        assert order_handler.call_count == 1
        assert validation_handler.call_count == 1
    
    @pytest.mark.asyncio
    async def test_unsubscribe_stops_receiving_events(self, event_bus, sample_order_event):
        """
        Test that unsubscribed handlers stop receiving events.
        
        This tests subscription lifecycle management:
        - Can subscribe to events
        - Can unsubscribe from events
        - Unsubscribed handlers no longer receive events
        """
        # === ARRANGE ===
        handler = AsyncMock()
        subscription_id = event_bus.subscribe(OrderCreatedEvent, handler)
        
        # === ACT & ASSERT - Part 1 ===
        # First verify handler receives events when subscribed
        await event_bus.publish(sample_order_event)
        handler.assert_called_once()
        
        # === ACT - Part 2 ===
        # Unsubscribe the handler
        event_bus.unsubscribe(subscription_id)
        
        # reset_mock() clears call history but keeps configuration
        handler.reset_mock()
        
        # Publish another event
        await event_bus.publish(sample_order_event)
        
        # === ASSERT - Part 2 ===
        # Handler should NOT be called after unsubscribe
        handler.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_exception_in_handler_doesnt_stop_other_handlers(self, event_bus):
        """
        Test resilience: if one handler fails, others should still execute.
        
        This is CRITICAL for financial systems:
        - One service failure shouldn't cascade
        - System should be resilient to partial failures
        - Bad handlers shouldn't break good ones
        
        Real-world scenario:
        - Risk service fails but order service should still process
        - Notification service fails but trade should still execute
        """
        # === ARRANGE ===
        # Create handler that always raises exception
        failing_handler = AsyncMock(side_effect=Exception("Handler failed!"))
        successful_handler = AsyncMock()
        
        # Subscribe both handlers
        event_bus.subscribe(OrderCreatedEvent, failing_handler)
        event_bus.subscribe(OrderCreatedEvent, successful_handler)
        
        event = OrderCreatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            order_id="123",
            symbol="AAPL",
            quantity=Decimal("100"),
            price=Decimal("150.50"),
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            account_id=None,
            metadata={}
        )
        
        # === ACT ===
        # This should not raise exception despite handler failure
        await event_bus.publish(event)
        
        # === ASSERT ===
        # Both handlers should be called
        successful_handler.assert_called_once_with(event)
        failing_handler.assert_called_once_with(event)
        # Failing handler threw exception but didn't stop successful handler


# ============================================
# PROPERTY-BASED TESTING WITH HYPOTHESIS
# ============================================

class TestOrderValidation:
    """
    Property-based testing ensures our business logic holds for ALL valid inputs.
    
    Traditional testing: Test specific examples
    Property testing: Test properties that should always hold
    
    Benefits:
    1. Finds edge cases you didn't think of
    2. Tests with hundreds of random inputs
    3. Automatically shrinks failing cases to minimal example
    4. Better coverage of input space
    """
    
    @given(
        # Hypothesis strategies generate random test data
        # decimals() generates random Decimal values within constraints
        quantity=decimals(
            min_value=Decimal("0.01"),  # Minimum valid quantity
            max_value=Decimal("10000"),  # Maximum reasonable quantity
            places=2  # Decimal places (cents)
        ),
        price=decimals(
            min_value=Decimal("0.01"),  # Penny stocks
            max_value=Decimal("10000"),  # Expensive stocks (BRK.A)
            places=2
        )
    )
    @settings(max_examples=100)  # Run 100 random test cases
    def test_order_notional_value_calculation(self, quantity, price):
        """
        Property: notional value should always equal quantity * price.
        
        This is a mathematical invariant that must ALWAYS hold.
        Hypothesis will test with 100 different random values.
        
        If this fails, Hypothesis will:
        1. Find the failing case
        2. Shrink it to minimal example
        3. Report the simplest failing input
        """
        # Create order with random inputs and all required fields
        order = OrderCreatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            order_id="TEST-001",
            symbol="AAPL",
            quantity=quantity,  # Random from Hypothesis
            price=price,  # Random from Hypothesis
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            account_id=None,
            metadata={}
        )
        
        # Property assertions - must hold for ALL valid inputs
        assert order.notional_value == quantity * price
        assert order.notional_value > 0  # Always positive for valid inputs
        
        # This catches calculation errors that might only appear
        # with specific values (e.g., rounding errors)
    
    @given(
        # text() strategy generates random strings
        symbol=text(
            min_size=1,  # At least 1 character
            max_size=10,  # At most 10 characters
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # Stock symbols are uppercase
        ),
        quantity=decimals(min_value=Decimal("1"), max_value=Decimal("10000")),
        price=decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"))
    )
    def test_order_serialization_roundtrip(self, symbol, quantity, price):
        """
        Property: serialization and deserialization should preserve all data.
        
        This is critical for event sourcing:
        - Events must be perfectly recoverable from storage
        - No data loss during serialization
        - This tests our to_message/from_message methods
        
        The round-trip property: deserialize(serialize(x)) == x
        """
        # Create order with random data
        original_order = OrderCreatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            order_id="TEST-001",
            symbol=symbol,
            quantity=quantity,
            price=price,
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            account_id=None,
            metadata={}
        )
        
        # Serialize to dict (simulating Kafka/database storage)
        serialized = original_order.to_message()
        
        # Deserialize back to object
        deserialized_order = OrderCreatedEvent.from_message(serialized)
        
        # All properties should be preserved
        assert deserialized_order.order_id == original_order.order_id
        assert deserialized_order.symbol == original_order.symbol
        assert deserialized_order.quantity == original_order.quantity
        assert deserialized_order.price == original_order.price
        assert deserialized_order.notional_value == original_order.notional_value