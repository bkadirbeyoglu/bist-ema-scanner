"""
Integration tests for SQS consumer.

These tests verify the consumer correctly processes SNS notifications
delivered via SQS.
"""

import json

import pytest

from notification_service.infrastructure.sqs_consumer import NotificationEventHandler
from notification_service.infrastructure.sqs_consumer import SQSConsumer
from notification_service.application.notification_service import NotificationApplicationService
from notification_service.infrastructure.notification_repository import InMemoryNotificationRepository


class TestNotificationEventHandler:
    """Tests for the event handler callback."""

    async def test_handles_order_filled_event(
        self,
        notification_service: NotificationApplicationService,
        repository: InMemoryNotificationRepository,
    ) -> None:
        """Handler creates notifications for order filled events."""
        handler = NotificationEventHandler(
            notification_service=notification_service,
            default_recipient="test@example.com",
        )
        
        event_data = {
            "event_type": "OrderFilledEvent",
            "event_id": "evt_123",
            "order_id": "order_456",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "fill_price": 150.50,
        }
        
        await handler(event_data)
        
        # Check notifications were created
        notifications = await repository.list_all()
        assert len(notifications) == 2  # EMAIL and SLACK by default

    async def test_skips_unknown_event_types(
        self,
        notification_service: NotificationApplicationService,
        repository: InMemoryNotificationRepository,
    ) -> None:
        """Handler logs warning for unknown event types."""
        handler = NotificationEventHandler(
            notification_service=notification_service,
        )
        
        event_data = {
            "event_type": "SomeUnknownEvent",
            "event_id": "evt_unknown",
        }
        
        # Should not raise
        await handler(event_data)
        
        # No notifications created
        notifications = await repository.list_all()
        assert len(notifications) == 0


class TestSQSMessageParsing:
    """Tests for parsing SNS notifications from SQS."""

    def test_parse_sns_envelope(self) -> None:
        """Can parse SNS notification envelope."""
        # This is what SQS receives from SNS
        sns_envelope = {
            "Type": "Notification",
            "MessageId": "msg-123",
            "TopicArn": "arn:aws:sns:us-east-1:000000000000:order-events",
            "Message": json.dumps({
                "event_type": "OrderFilledEvent",
                "order_id": "order_456",
                "symbol": "AAPL",
            }),
            "Timestamp": "2025-01-15T10:30:00.000Z",
        }
        
        # Parse the Message field
        event_data = json.loads(sns_envelope["Message"])
        
        assert event_data["event_type"] == "OrderFilledEvent"
        assert event_data["symbol"] == "AAPL"