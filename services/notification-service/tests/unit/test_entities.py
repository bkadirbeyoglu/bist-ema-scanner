"""
Tests for Notification entity.

The Notification is the aggregate root of this bounded context.
"""

import pytest

from notification_service.domain.entities import Notification
from notification_service.domain.entities import NotificationRecipient
from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationPriority
from notification_service.domain.value_objects import NotificationStatus
from notification_service.domain.value_objects import NotificationType
from notification_service.domain.value_objects import create_notification_id


class TestNotificationRecipient:
    """Tests for NotificationRecipient value object."""

    def test_recipient_is_immutable_value_object(self) -> None:
        """Recipient is frozen dataclass with value equality."""
        r1 = NotificationRecipient(address="user@example.com", name="John")
        r2 = NotificationRecipient(address="user@example.com", name="John")
        
        # Value equality
        assert r1 == r2
        
        # Immutable
        with pytest.raises(AttributeError):
            r1.address = "other@example.com"  # type: ignore


class TestNotification:
    """Tests for Notification aggregate."""

    def test_notification_creation_and_defaults(self) -> None:
        """Notification has sensible defaults."""
        notification = Notification(
            id=create_notification_id(),
            notification_type=NotificationType.ORDER_FILLED,
            channel=NotificationChannel.EMAIL,
            recipient=NotificationRecipient(address="user@example.com"),
            subject="Order Filled",
            body="Your order has been filled.",
        )
        
        assert notification.status == NotificationStatus.PENDING
        assert notification.priority == NotificationPriority.NORMAL
        assert notification.created_at is not None
        assert notification.sent_at is None

    def test_notification_lifecycle(self) -> None:
        """Notification status transitions: PENDING -> SENT -> DELIVERED/FAILED."""
        notification = Notification(
            id=create_notification_id(),
            notification_type=NotificationType.ORDER_FILLED,
            channel=NotificationChannel.EMAIL,
            recipient=NotificationRecipient(address="user@example.com"),
            subject="Test",
            body="Test body",
        )
        
        # Initial state
        assert notification.status == NotificationStatus.PENDING
        
        # Mark sent
        notification.mark_as_sent()
        assert notification.status == NotificationStatus.SENT
        assert notification.sent_at is not None
        
        # Mark delivered
        notification.mark_as_delivered()
        assert notification.status == NotificationStatus.DELIVERED

    def test_notification_failure(self) -> None:
        """Failed notifications capture error message."""
        notification = Notification(
            id=create_notification_id(),
            notification_type=NotificationType.ORDER_FILLED,
            channel=NotificationChannel.SMS,
            recipient=NotificationRecipient(address="+1234567890"),
            subject="Alert",
            body="Trade executed",
        )
        
        notification.mark_as_failed("Invalid phone number")
        
        assert notification.status == NotificationStatus.FAILED
        assert notification.error_message == "Invalid phone number"

    def test_notification_to_dict(self) -> None:
        """Serialization uses StrEnum string values automatically."""
        notification = Notification(
            id=create_notification_id(),
            notification_type=NotificationType.ORDER_FILLED,
            channel=NotificationChannel.EMAIL,
            recipient=NotificationRecipient(address="user@example.com"),
            subject="Order Filled",
            body="Your order has been filled.",
            metadata={"order_id": "order_123"},
            reference_id="evt_abc123",
        )
        
        data = notification.to_dict()
        
        # StrEnum serializes as string
        assert data["notification_type"] == "order_filled"
        assert data["channel"] == "email"
        assert data["metadata"]["order_id"] == "order_123"
        assert data["reference_id"] == "evt_abc123"