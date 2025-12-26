"""
Tests for NotificationApplicationService.

Uses fixtures from conftest.py.
"""

import pytest

from notification_service.application.notification_service import NotificationApplicationService
from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationStatus
from notification_service.domain.value_objects import NotificationType


class TestNotificationApplicationService:
    """Tests for the notification application service."""

    async def test_handle_order_event_creates_notifications(
        self,
        notification_service: NotificationApplicationService,
        sample_order_filled_event: dict,
    ) -> None:
        """Service creates one notification per channel, marked as sent."""
        results = await notification_service.handle_order_event(
            event_data=sample_order_filled_event,
            channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
            recipient_address="user@example.com",
        )
        
        # One per channel
        assert len(results) == 2
        
        # Correct type and status
        for r in results:
            assert r.notification.notification_type == NotificationType.ORDER_FILLED
            assert r.notification.status == NotificationStatus.SENT
            assert r.notification.reference_id == "evt_test_123"

    async def test_unknown_event_type_raises(
        self,
        notification_service: NotificationApplicationService,
    ) -> None:
        """Unknown event types raise ValueError."""
        with pytest.raises(ValueError, match="Unknown event type"):
            await notification_service.handle_order_event(
                event_data={"event_type": "UnknownEvent"},
                channels=[NotificationChannel.EMAIL],
                recipient_address="user@example.com",
            )

    async def test_list_and_stats(
        self,
        notification_service: NotificationApplicationService,
        sample_order_filled_event: dict,
    ) -> None:
        """Can list notifications and get statistics."""
        await notification_service.handle_order_event(
            event_data=sample_order_filled_event,
            channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
            recipient_address="user@example.com",
        )
        
        # List
        notifications = await notification_service.list_notifications()
        assert len(notifications) == 2
        
        # Stats
        stats = await notification_service.get_stats()
        assert stats[NotificationStatus.SENT] == 2