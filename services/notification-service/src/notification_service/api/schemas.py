"""
API schemas (Pydantic models) for request/response validation.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RecipientResponse(BaseModel):
    """Recipient in API response."""
    
    address: str
    name: str | None = None


class NotificationResponse(BaseModel):
    """Single notification in API response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    notification_type: str
    channel: str
    recipient: RecipientResponse
    subject: str
    body: str
    status: str
    priority: str
    created_at: datetime
    sent_at: datetime | None = None
    metadata: dict[str, Any] = {}
    reference_id: str | None = None
    error_message: str | None = None


class NotificationListResponse(BaseModel):
    """Response for listing notifications."""
    
    notifications: list[NotificationResponse]
    total: int


class NotificationStatsResponse(BaseModel):
    """Response for notification statistics."""
    
    total: int
    by_status: dict[str, int]


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str
    service: str
    version: str = "0.1.0"
    consumer_running: bool = False