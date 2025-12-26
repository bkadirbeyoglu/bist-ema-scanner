"""
Tests for notification templates.

Templates render human-readable messages from event data.
"""

import pytest

from notification_service.application.templates import OrderCreatedTemplate
from notification_service.application.templates import OrderFilledTemplate
from notification_service.application.templates import TemplateRegistry
from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationType


class TestTemplates:
    """Tests for notification templates."""

    def test_order_filled_renders_for_all_channels(self) -> None:
        """OrderFilledTemplate renders appropriate content per channel."""
        template = OrderFilledTemplate()
        data = {
            "order_id": "order_123",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "fill_price": 150.50,
        }
        
        # Email - full details
        email = template.render(NotificationChannel.EMAIL, data)
        assert email.subject == "Order Filled: AAPL"
        assert "order_123" in email.body
        
        # Slack - emoji formatting
        slack = template.render(NotificationChannel.SLACK, data)
        assert "📈" in slack.subject  # buy = up arrow
        
        # SMS - short (under 160 chars)
        sms = template.render(NotificationChannel.SMS, data)
        assert len(sms.body) <= 160

    def test_templates_handle_missing_data(self) -> None:
        """Templates use safe_substitute to handle missing keys."""
        template = OrderFilledTemplate()
        
        result = template.render(
            channel=NotificationChannel.EMAIL,
            data={"symbol": "TSLA"},  # Missing most fields
        )
        
        # Should not raise, uses defaults
        assert "TSLA" in result.body


class TestTemplateRegistry:
    """Tests for template registry."""

    def test_registry_returns_correct_template(self) -> None:
        """Registry maps notification types to templates."""
        registry = TemplateRegistry()
        
        assert isinstance(
            registry.get_template(NotificationType.ORDER_FILLED),
            OrderFilledTemplate,
        )
        assert isinstance(
            registry.get_template(NotificationType.ORDER_CREATED),
            OrderCreatedTemplate,
        )
        assert registry.get_template(NotificationType.SYSTEM_ALERT) is None