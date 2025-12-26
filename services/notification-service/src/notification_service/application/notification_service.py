"""
Notification Application Service.

Orchestrates notification creation, template rendering, and delivery.
"""

import logging
from dataclasses import dataclass
from typing import Any

from notification_service.application.templates import TemplateRegistry
from notification_service.domain.entities import Notification, NotificationRecipient
from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationId
from notification_service.domain.value_objects import NotificationStatus
from notification_service.domain.value_objects import NotificationType
from notification_service.domain.value_objects import create_notification_id
from notification_service.infrastructure.notification_repository import InMemoryNotificationRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationCreated:
    """Result of creating a notification."""
    
    notification: Notification
    channel_log: str


# Map event type string to NotificationType enum
EVENT_TYPE_MAP: dict[str, NotificationType] = {
    "OrderCreatedEvent": NotificationType.ORDER_CREATED,
    "OrderFilledEvent": NotificationType.ORDER_FILLED,
    "OrderPartiallyFilledEvent": NotificationType.ORDER_PARTIALLY_FILLED,
    "OrderCancelledEvent": NotificationType.ORDER_CANCELLED,
    "OrderRejectedEvent": NotificationType.ORDER_REJECTED,
}


class NotificationApplicationService:
    """
    Application service for notification management.
    
    Responsibilities:
    - Handle incoming order events
    - Create notifications with appropriate templates
    - "Send" notifications (simulated for demo)
    - Query notification history
    """

    def __init__(
        self, 
        repository: InMemoryNotificationRepository, 
        template_registry: TemplateRegistry | None = None,
    ) -> None:
        """"Initialize application service."""
        self._repository = repository
        self._templates = template_registry or TemplateRegistry()

    async def handle_order_event(
        self,
        event_data: dict[str, Any],
        channels: list[NotificationChannel],
        recipient_address: str,
        recipient_name: str | None = None,
    ) -> list[NotificationCreated]:
        """
        Handle an order event and create notifications.
        
        Creates one notification per channel from the event data.
        """
        event_type_str = event_data.get("event_type", "")
        
        if event_type_str not in EVENT_TYPE_MAP:
            raise ValueError(f"Unknown event type: {event_type_str}")
        
        notification_type = EVENT_TYPE_MAP[event_type_str]
        template = self._templates.get_template(notification_type)
        
        results: list[NotificationCreated] = []
        
        for channel in channels:
            notification = await self._create_notification(
                notification_type=notification_type,
                channel=channel,
                recipient_address=recipient_address,
                recipient_name=recipient_name,
                event_data=event_data,
                template=template,
            )
            
            channel_log = self._simulate_send(notification, channel)
            notification.mark_as_sent()
            
            await self._repository.save(notification)
            
            results.append(NotificationCreated(
                notification=notification,
                channel_log=channel_log,
            ))
            
            logger.info(
                "Notification sent",
                extra={
                    "notification_id": notification.id,
                    "type": str(notification_type),
                    "channel": str(channel),
                },
            )
        
        return results
    
    async def _create_notification(
        self,
        notification_type: NotificationType,
        channel: NotificationChannel,
        recipient_address: str,
        recipient_name: str | None,
        event_data: dict[str, Any],
        template: Any,
    ) -> Notification:
        """Create notification with rendered content."""
        
        if template is not None:
            rendered = template.render(channel=channel, data=event_data)
            subject = rendered.subject
            body = rendered.body
        else:
            subject = f"Notification: {notification_type}"
            body = f"Event: {event_data}"
        
        return Notification(
            id=create_notification_id(),
            notification_type=notification_type,
            channel=channel,
            recipient=NotificationRecipient(
                address=recipient_address,
                name=recipient_name,
            ),
            subject=subject,
            body=body,
            reference_id=event_data.get("event_id"),
            metadata=event_data,
        )
    
    def _simulate_send(
        self,
        notification: Notification,
        channel: NotificationChannel,
    ) -> str:
        """
        Simulate sending notification to channel.
        
        In production, this would call:
        - EMAIL: SendGrid, AWS SES
        - SLACK: Slack API
        - SMS: Twilio
        - PUSH: Firebase
        """
        channel_output = {
            NotificationChannel.EMAIL: (
                f"📧 EMAIL to {notification.recipient.address}\n"
                f"   Subject: {notification.subject}\n"
                f"   Body: {notification.body[:100]}..."
            ),
            NotificationChannel.SLACK: (
                f"💬 SLACK to {notification.recipient.address}\n"
                f"   {notification.body[:100]}..."
            ),
            NotificationChannel.SMS: (
                f"📱 SMS to {notification.recipient.address}\n"
                f"   {notification.body}"
            ),
            NotificationChannel.PUSH: (
                f"🔔 PUSH to {notification.recipient.address}\n"
                f"   Title: {notification.subject}"
            ),
        }
        
        log_message = channel_output.get(channel, f"Unknown channel: {channel}")
        logger.info(log_message)
        
        return log_message
    
    async def get_notification(
        self,
        notification_id: NotificationId,
    ) -> Notification | None:
        """Get notification by ID."""
        return await self._repository.get_by_id(notification_id)
    
    async def list_notifications(self, limit: int = 100) -> list[Notification]:
        """List all notifications."""
        return await self._repository.list_all(limit=limit)
    
    async def get_stats(self) -> dict[NotificationStatus, int]:
        """Get notification statistics by status."""
        return await self._repository.count_by_status()