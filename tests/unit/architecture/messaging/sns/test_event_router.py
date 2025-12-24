"""
Unit tests for Event Router with singledispatch.

Tests type-based event routing using Python's functools.singledispatch.
"""

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from trading_system.architecture.messaging.sns.event_router import EventRouter
from trading_system.architecture.messaging.sns.event_router import handle_event
from trading_system.shared_kernel.sns_events import OrderCreatedEvent
from trading_system.shared_kernel.sns_events import OrderFilledEvent
from trading_system.shared_kernel.sns_events import PriceUpdatedEvent


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def price_event() -> PriceUpdatedEvent:
    """Create a sample price event."""
    return PriceUpdatedEvent(
        symbol="AAPL",
        price=Decimal("178.50"),
        timestamp=datetime.now(timezone.utc),
        source="test",
    )


@pytest.fixture
def order_created_event() -> OrderCreatedEvent:
    """Create a sample order created event."""
    return OrderCreatedEvent(
        order_id=uuid4(),
        symbol="AAPL",
        side="buy",
        quantity=100,
        order_type="market",
    )


@pytest.fixture
def order_filled_event() -> OrderFilledEvent:
    """Create a sample order filled event."""
    return OrderFilledEvent(
        order_id=uuid4(),
        symbol="AAPL",
        side="buy",
        quantity=100,
        fill_price=Decimal("178.55"),
    )


# =============================================================================
# Test Cases for singledispatch
# =============================================================================

class TestHandleEventSingledispatch:
    """Tests for the handle_event singledispatch function."""

    def test_routes_price_updated_event(
        self,
        price_event: PriceUpdatedEvent,
    ) -> None:
        """Verify price events are routed to correct handler."""
        result = handle_event(price_event)

        assert result["handler"] == "price_updated"
        assert result["symbol"] == "AAPL"
        assert "price" in result

    def test_routes_order_created_event(
        self,
        order_created_event: OrderCreatedEvent,
    ) -> None:
        """Verify order created events are routed correctly."""
        result = handle_event(order_created_event)

        assert result["handler"] == "order_created"
        assert result["symbol"] == "AAPL"
        assert result["side"] == "buy"

    def test_routes_order_filled_event(
        self,
        order_filled_event: OrderFilledEvent,
    ) -> None:
        """Verify order filled events are routed correctly."""
        result = handle_event(order_filled_event)

        assert result["handler"] == "order_filled"
        assert result["fill_price"] == Decimal("178.55")

    def test_unknown_type_raises_not_implemented(self) -> None:
        """Verify unknown types raise NotImplementedError."""
        @dataclass
        class UnknownEvent:
            data: str

        with pytest.raises(NotImplementedError) as exc_info:
            handle_event(UnknownEvent(data="test"))

        assert "No handler registered" in str(exc_info.value)


# =============================================================================
# Test Cases for EventRouter Class
# =============================================================================

class TestEventRouter:
    """Tests for the EventRouter class wrapper."""

    def test_router_tracks_processed_count(
        self,
        price_event: PriceUpdatedEvent,
        order_created_event: OrderCreatedEvent,
    ) -> None:
        """Verify router tracks how many events were processed."""
        router = EventRouter()

        router.route(price_event)
        router.route(order_created_event)

        assert router.processed_count == 2

    def test_router_tracks_events_by_type(
        self,
        price_event: PriceUpdatedEvent,
        order_created_event: OrderCreatedEvent,
        order_filled_event: OrderFilledEvent,
    ) -> None:
        """Verify router maintains per-type statistics."""
        router = EventRouter()

        router.route(price_event)
        router.route(price_event)  # Second price event
        router.route(order_created_event)
        router.route(order_filled_event)

        stats = router.get_stats()

        assert stats["PriceUpdatedEvent"] == 2
        assert stats["OrderCreatedEvent"] == 1
        assert stats["OrderFilledEvent"] == 1

    def test_router_error_handling(self) -> None:
        """Verify router handles unknown events gracefully."""
        @dataclass
        class UnknownEvent:
            data: str

        router = EventRouter()
        result = router.route(UnknownEvent(data="test"))

        assert result["error"] is True
        assert "No handler registered" in result["message"]
        assert router.error_count == 1