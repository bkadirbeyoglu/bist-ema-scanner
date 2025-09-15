"""
Tests for Order entity - demonstrates entity vs value object differences.
"""

from decimal import Decimal
from datetime import datetime
from uuid import UUID
import pytest

from trading_system.domain.entities.order import Order, OrderType, OrderSide, OrderStatus
from trading_system.domain.value_objects.price import Price
from trading_system.domain.value_objects.symbol import Symbol


class TestOrder:
    """ Test suite for Order entity """

    def test_create_market_order(self):
        """ Test creating a market order """
        # Arrange 
        symbol = Symbol("AAPL")

        # Act - using factory method for cleaner creation
        order = Order.create_market_order(
            symbol=symbol,
            quantity=100,
            side=OrderSide.BUY
        )

        # Assert
        assert order.symbol == symbol
        assert order.quantity == 100
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.PENDING
        assert order.limit_price is None    # Market orders don't have limit price

        # Entities have identity (unique ID)
        assert isinstance(order.id, UUID)
        assert isinstance(order.created_at, datetime)

    def test_create_limit_order(self):
        """ Test creating a limit order """
        # Arrange
        symbol = Symbol("MSFT")
        limit_price = Price(Decimal("350.00"))

        # Act
        order = Order.create_limit_order(
            symbol=symbol,
            quantity=50,
            side=OrderSide.SELL,
            limit_price=limit_price
        )

        # Assert
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == limit_price

    def test_order_identity(self):
        """
        Test that each order has unique identity.
        This is key difference from value objects.
        """
        order1 = Order.create_market_order(Symbol("AAPL"), 100, OrderSide.BUY)
        order2 = Order.create_market_order(Symbol("AAPL"), 100, OrderSide.BUY)
        # Same attributes but different identity
        assert order1.id != order2.id
        assert order1 != order2     # Entities are compared by ID

    def test_order_state_changes(self):
        """
        Test that order can change state (mutable).
        Entities can change over time, unlike value objects.
        """
        order = Order.create_market_order(Symbol("AAPL"), 100, OrderSide.BUY)

        # Initial state
        assert order.status == OrderStatus.PENDING

        # Submit order - state changes
        order.submit()
        assert order.status == OrderStatus.SUBMITTED
        assert order.submitted_at is not None

        # Fill order - more state changes
        fill_price = Price(Decimal("150.00"))
        order.fill(fill_price)
        assert order.status == OrderStatus.FILLED
        assert order.fill_price == fill_price
        assert order.filled_at is not None

    def test_order_validation(self):
        """ Test order validation rules """
        # Quantity must be positive
        with pytest.raises(ValueError, match="Quantity must be positive"):
            Order.create_market_order(Symbol("AAPL"), 0, OrderSide.BUY)

        with pytest.raises(ValueError, match="Quantity must be positive"):
            Order.create_market_order(Symbol("AAPL"), -10, OrderSide.BUY)

    def test_cannot_fill_before_submit(self):
        """ Test business rule: order must be submitted before filling """
        order = Order.create_market_order(Symbol("AAPL"), 100, OrderSide.BUY)

        # Try to fill before submitting
        with pytest.raises(ValueError, match=f"Cannot fill order in {OrderStatus.PENDING} status"):
            order.fill(Price(Decimal("150.00")))
        