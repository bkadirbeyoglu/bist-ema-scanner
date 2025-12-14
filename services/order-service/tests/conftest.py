"""
Shared test fixtures for Order Service tests.

This file is automatically discovered by pytest and fixtures
defined here are available to all test files.
"""

import pytest
from decimal import Decimal

from order_service.domain.entities import Order, OrderSide, OrderType


@pytest.fixture
def sample_order() -> Order:
    """
    Create a sample order for testing.
    
    This fixture is used by both unit and integration tests.
    Each test gets a fresh order instance.
    """
    return Order(
        id="test-order-001",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("100"),
        account_id="account-001"
    )


@pytest.fixture
def large_order() -> Order:
    """
    Create an order that will fail risk checks (too large).
    
    At mock price of $150, 1000 shares = $150,000 which exceeds
    the $100,000 risk limit. But 1000 < 1,000,000 so it passes
    the quantity validation in step 1.
    """
    return Order(
        id="test-order-large",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1000"),  # $150k at $150/share > $100k risk limit
        account_id="account-001"
    )


@pytest.fixture
def limit_order() -> Order:
    """Create a limit order for testing."""
    return Order(
        id="test-order-limit",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("50"),
        limit_price=Decimal("145.00"),
        account_id="account-001"
    )