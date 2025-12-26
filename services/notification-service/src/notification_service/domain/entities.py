"""
Domain entities for the Notification Service.

The Notification aggregate is the core entity of this bounded context.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypeAlias

from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationId
from notification_service.domain.value_objects import NotificationPriority
from notification_service.domain.value_objects import NotificationStatus
from notification_service.domain.value_objects import NotificationType


# =============================================================================
# Type Aliases
# =============================================================================
# TypeAlias documents that a name is a type alias (not a variable).
# This is optional but makes code clearer and helps IDEs.

MetadataDict: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class NotificationRecipient:
    """
    Recipient information for a notification.
    
    This is a value object (immutable, compared by value).
    The meaning of 'address' varies by channel:
    - EMAIL: email address
    - SLACK: channel name (e.g., "#trading-alerts") or user ID
    - SMS: phone number
    - PUSH: device token
    
    Attributes:
        address: The delivery address for this channel
        name: Optional display name for personalization
    """
    
    address: str
    name: str | None = None

@dataclass
class Notification:
    """
    Notification aggregate root.
    
    Represents a notification to be sent (or that has been sent) to a user.
    This is the aggregate root of the Notification bounded context.
    
    Lifecycle:
        1. Created with status PENDING
        2. Sent to channel (status -> SENT)
        3. Delivery confirmed (status -> DELIVERED) or failed (status -> FAILED)
    
    Note: We use notification_type instead of type to avoid shadowing
    Python's built-in type() function.
    """
    
    # Required fields (no defaults)
    id: NotificationId
    notification_type: NotificationType  # Avoid 'type' - would shadow Python's built-in type()
    channel: NotificationChannel
    recipient: NotificationRecipient
    subject: str
    body: str
    
    # Fields with defaults
    status: NotificationStatus = NotificationStatus.PENDING
    priority: NotificationPriority = NotificationPriority.NORMAL
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: datetime | None = None
    metadata: MetadataDict = field(default_factory=dict)
    reference_id: str | None = None
    error_message: str | None = None
    
    def mark_as_sent(self) -> None:
        """Mark notification as sent to delivery channel."""
        self.status = NotificationStatus.SENT
        self.sent_at = datetime.now(timezone.utc)
    
    def mark_as_delivered(self) -> None:
        """Mark notification as successfully delivered."""
        self.status = NotificationStatus.DELIVERED
    
    def mark_as_failed(self, error: str) -> None:
        """Mark notification as failed with error message."""
        self.status = NotificationStatus.FAILED
        self.error_message = error
    
    def to_dict(self) -> dict[str, Any]:
        """
        Serialize notification to dictionary.
        
        StrEnum values serialize as strings automatically because
        they ARE strings. No need for .value conversion.
        """
        return {
            "id": self.id,
            "notification_type": self.notification_type,
            "channel": self.channel,
            "recipient": {
                "address": self.recipient.address,
                "name": self.recipient.name,
            },
            "subject": self.subject,
            "body": self.body,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "metadata": self.metadata,
            "reference_id": self.reference_id,
            "error_message": self.error_message,
        }