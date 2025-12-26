"""
Pytest configuration and shared fixtures for Notification Service tests.

This file is automatically loaded by pytest. Fixtures defined here
are available to all test files without explicit imports.

NOTE: We start with sample event fixtures only. Repository and service
fixtures will be added in Part 4 when those components are implemented.
"""

import pytest

from notification_service.infrastructure.notification_repository import InMemoryNotificationRepository
from notification_service.application.notification_service import NotificationApplicationService
from notification_service.application.templates import TemplateRegistry


# =============================================================================
# Sample Event Fixtures
# =============================================================================
# These fixtures provide test data for order events (as they arrive from SNS).
# They don't depend on any service code, so they work from the start.

@pytest.fixture
def sample_order_filled_event() -> dict:
    """Sample OrderFilledEvent data for testing."""
    return {
        "event_type": "OrderFilledEvent",
        "event_id": "evt_test_123",
        "order_id": "order_test_456",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 100,
        "fill_price": 150.50,
        "filled_at": "2025-01-15T10:30:00Z",
    }


@pytest.fixture
def sample_order_created_event() -> dict:
    """Sample OrderCreatedEvent data for testing."""
    return {
        "event_type": "OrderCreatedEvent",
        "event_id": "evt_test_789",
        "order_id": "order_test_new",
        "symbol": "GOOGL",
        "side": "sell",
        "quantity": 50,
        "order_type": "limit",
        "limit_price": 175.00,
    }


@pytest.fixture
def sample_order_cancelled_event() -> dict:
    """Sample OrderCancelledEvent data for testing."""
    return {
        "event_type": "OrderCancelledEvent",
        "event_id": "evt_test_cancel",
        "order_id": "order_test_cancel",
        "symbol": "MSFT",
        "reason": "User requested cancellation",
    }

@pytest.fixture
def repository() -> InMemoryNotificationRepository:
    """
    Create a fresh in-memory repository for each test.
    
    Using a fresh instance ensures test isolation - no state
    leaks between tests.
    """
    return InMemoryNotificationRepository()


@pytest.fixture
def template_registry() -> TemplateRegistry:
    """Create template registry with default templates."""
    return TemplateRegistry()


@pytest.fixture
def notification_service(
    repository: InMemoryNotificationRepository,
    template_registry: TemplateRegistry,
) -> NotificationApplicationService:
    """
    Create notification service with test dependencies.
    
    This fixture composes repository and template_registry fixtures,
    demonstrating pytest's fixture dependency injection.
    """
    return NotificationApplicationService(
        repository=repository,
        template_registry=template_registry,
    )