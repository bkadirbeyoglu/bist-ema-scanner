"""
Domain value objects for the Notification Service.

Value objects are immutable and defined by their attributes rather than identity.
We use StrEnum for enumerated values and NewType for type-safe identifiers.
"""

import uuid
from enum import StrEnum
from typing import NewType


# =============================================================================
# NewType Definition
# =============================================================================
# Creates distinct type for type checking (zero runtime overhead).
# See "Understanding NewType" section above for detailed explanation.

NotificationId = NewType("NotificationId", str)


def create_notification_id() -> NotificationId:
    """
    Create a new unique notification ID.
    
    Format: notif_{uuid4}
    """
    return NotificationId(f"notif_{uuid.uuid4()}")

# =============================================================================
# StrEnum Definitions
# =============================================================================
# StrEnum (Python 3.11+) creates enums that ARE strings.
# See "Understanding StrEnum" section above for detailed explanation.


class NotificationChannel(StrEnum):
    """
    Available notification delivery channels.
    
    In production, each integrates with external services:
    EMAIL (SendGrid/SES), SLACK (Slack API), SMS (Twilio), PUSH (Firebase)
    """
    
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    PUSH = "push"


class NotificationStatus(StrEnum):
    """Notification delivery status lifecycle: PENDING -> SENT -> DELIVERED/FAILED"""
    
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class NotificationPriority(StrEnum):
    """Notification priority levels."""
    
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationType(StrEnum):
    """Types of notifications based on triggering events."""
    
    ORDER_CREATED = "order_created"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    PRICE_ALERT = "price_alert"
    SYSTEM_ALERT = "system_alert"