"""
Integration tests for the Notification Service REST API.
"""

import pytest
from httpx import AsyncClient
from httpx import ASGITransport

# =============================================================================
# CRITICAL: Import order matters!
# =============================================================================
#
# We must import get_notification_service from router.py BEFORE importing
# from main.py. Here's why:
#
#   1. router.py defines: get_notification_service = _get_service_placeholder
#   2. Routes use: Depends(get_notification_service)  # Captures placeholder
#   3. main.py replaces: router_module.get_notification_service = real_func
#
# If we import from main.py first, it runs and replaces the placeholder.
# Then when we import get_notification_service, we get the WRONG function!
#
# FastAPI's Depends() still has the ORIGINAL placeholder, so we need that
# as the key for dependency_overrides.
#

# Import placeholder FIRST (before main.py replaces it)
from notification_service.api.router import get_notification_service as _placeholder

# NOW import app (this runs main.py which replaces the placeholder)
from notification_service.main import app

from notification_service.application.notification_service import NotificationApplicationService
from notification_service.infrastructure.notification_repository import InMemoryNotificationRepository
from notification_service.domain.entities import Notification
from notification_service.domain.entities import NotificationRecipient
from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationType
from notification_service.domain.value_objects import create_notification_id


@pytest.fixture
async def client(
    notification_service: NotificationApplicationService,
) -> AsyncClient:
    """Create async test client with overridden dependencies."""
    # Use the ORIGINAL placeholder as the key (what FastAPI captured)
    app.dependency_overrides[_placeholder] = lambda: notification_service
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    # Clean up - remove the override
    app.dependency_overrides.clear()


class TestNotificationAPI:
    """Tests for Notification Service REST API."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """Health endpoint returns service info."""
        response = await client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    async def test_list_and_get_notifications(
        self,
        client: AsyncClient,
        repository: InMemoryNotificationRepository,
    ) -> None:
        """Can list notifications and get by ID."""
        # Empty initially
        response = await client.get("/notifications")
        assert response.json()["total"] == 0
        
        # Add one
        notif = Notification(
            id=create_notification_id(),
            notification_type=NotificationType.ORDER_FILLED,
            channel=NotificationChannel.EMAIL,
            recipient=NotificationRecipient(address="user@example.com"),
            subject="Test",
            body="Test body",
        )
        await repository.save(notif)
        
        # Now listed
        response = await client.get("/notifications")
        assert response.json()["total"] == 1
        
        # 404 for unknown
        response = await client.get("/notifications/notif_nonexistent")
        assert response.status_code == 404

    async def test_notification_stats(self, client: AsyncClient) -> None:
        """Stats endpoint returns counts."""
        response = await client.get("/notifications/stats")
        
        assert response.status_code == 200
        assert response.json()["total"] == 0