"""
Domain events for the Notification Service.

These events represent significant occurrences within the notification domain.
They could be published for audit logging or integration with other services.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationId
from notification_service.domain.value_objects import NotificationStatus
from notification_service.domain.value_objects import NotificationType


@dataclass(frozen=True)
class NotificationEvent:
    """Base class for notification domain events."""
    
    notification_id: NotificationId
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class NotificationCreatedEvent(NotificationEvent):
    """Raised when a new notification is created."""
    
    notification_type: NotificationType
    channel: NotificationChannel
    recipient_address: str
    reference_id: str | None = None


@dataclass(frozen=True)
class NotificationSentEvent(NotificationEvent):
    """Raised when a notification is sent to the delivery channel."""
    
    channel: NotificationChannel


@dataclass(frozen=True)
class NotificationDeliveredEvent(NotificationEvent):
    """Raised when delivery is confirmed."""
    
    channel: NotificationChannel


@dataclass(frozen=True)
class NotificationFailedEvent(NotificationEvent):
    """Raised when notification delivery fails."""
    
    channel: NotificationChannel
    error_message: str