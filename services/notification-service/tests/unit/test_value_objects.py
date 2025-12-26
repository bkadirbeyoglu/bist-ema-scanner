"""
Tests for domain value objects.

Testing StrEnum and NewType patterns for notification domain.
"""

import json

import pytest

from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationId
from notification_service.domain.value_objects import NotificationPriority
from notification_service.domain.value_objects import NotificationStatus
from notification_service.domain.value_objects import NotificationType
from notification_service.domain.value_objects import create_notification_id


class TestStrEnumBehavior:
    """Tests demonstrating StrEnum advantages over regular Enum."""

    def test_strenum_is_a_string(self) -> None:
        """StrEnum members work as strings without .value."""
        channel = NotificationChannel.EMAIL
        
        # Direct string comparison
        assert channel == "email"
        
        # F-string formatting
        assert f"via {channel}" == "via email"
        
        # JSON serialization (would fail with regular Enum!)
        assert json.dumps({"channel": channel}) == '{"channel": "email"}'
        
        # isinstance checks
        assert isinstance(channel, str)
        assert isinstance(channel, NotificationChannel)

    def test_strenum_from_string(self) -> None:
        """Can create StrEnum from string (useful for API input)."""
        channel = NotificationChannel("slack")
        assert channel == NotificationChannel.SLACK
        
        with pytest.raises(ValueError):
            NotificationChannel("invalid")

    def test_all_enum_values_exist(self) -> None:
        """Verify all expected enum values are defined."""
        # Channels
        assert set(NotificationChannel) == {"email", "slack", "sms", "push"}
        
        # Status lifecycle
        assert set(NotificationStatus) == {"pending", "sent", "delivered", "failed"}
        
        # Priority levels
        assert set(NotificationPriority) == {"low", "normal", "high", "urgent"}
        
        # Notification types
        assert NotificationType.ORDER_FILLED == "order_filled"
        assert NotificationType.ORDER_CANCELLED == "order_cancelled"


class TestNotificationId:
    """Tests for NotificationId NewType."""

    def test_create_notification_id(self) -> None:
        """create_notification_id generates unique prefixed IDs."""
        id1 = create_notification_id()
        id2 = create_notification_id()
        
        # Has prefix
        assert id1.startswith("notif_")
        
        # Is unique
        assert id1 != id2
        
        # Is a string at runtime (NewType has zero overhead)
        assert isinstance(id1, str)