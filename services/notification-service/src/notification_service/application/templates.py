"""
Notification templates.

Templates render human-readable messages from event data for different channels.
Uses string.Template for safe string substitution.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from string import Template
from typing import Any

from notification_service.domain.value_objects import NotificationChannel
from notification_service.domain.value_objects import NotificationType


@dataclass(frozen=True)
class TemplateResult:
    """Result of template rendering."""
    
    subject: str
    body: str


class NotificationTemplate(ABC):
    """
    Base class for notification templates.
    
    Each template handles one NotificationType and renders
    different content for each NotificationChannel.
    """
    
    notification_type: NotificationType
    
    @abstractmethod
    def render(
        self,
        channel: NotificationChannel,
        data: dict[str, Any],
    ) -> TemplateResult:
        """Render notification content for a channel."""
        pass
    
    def _safe_get(self, data: dict[str, Any], key: str, default: str = "N/A") -> Any:
        """Safely get value from data dict with default."""
        return data.get(key, default)


class OrderFilledTemplate(NotificationTemplate):
    """Template for order filled notifications."""
    
    notification_type = NotificationType.ORDER_FILLED
    
    # string.Template uses $variable_name for substitution
    # safe_substitute() won't raise on missing keys
    EMAIL_SUBJECT = Template("Order Filled: $symbol")
    EMAIL_BODY = Template("""
Your order has been filled.

Order Details:
- Order ID: $order_id
- Symbol: $symbol
- Side: $side
- Quantity: $quantity shares
- Fill Price: $$fill_price
- Time: $filled_at

Thank you for trading with us.
""".strip())
    
    SLACK_BODY = Template("""
*Order Filled* $emoji

- *Symbol:* `$symbol`
- *Side:* $side
- *Quantity:* $quantity
- *Price:* $$fill_price
- *Order ID:* `$order_id`
""".strip())
    
    SMS_BODY = Template("Order filled: $side $quantity $symbol @ $$fill_price")
    
    def render(
        self,
        channel: NotificationChannel,
        data: dict[str, Any],
    ) -> TemplateResult:
        """Render order filled notification."""
        
        template_data = {
            "order_id": self._safe_get(data, "order_id"),
            "symbol": self._safe_get(data, "symbol"),
            "side": self._safe_get(data, "side", "unknown"),
            "quantity": self._safe_get(data, "quantity", 0),
            "fill_price": self._safe_get(data, "fill_price", "0.00"),
            "filled_at": self._safe_get(data, "filled_at", "unknown"),
            "emoji": "📈" if self._safe_get(data, "side") == "buy" else "📉",
        }
        
        if channel == NotificationChannel.EMAIL:
            return TemplateResult(
                subject=self.EMAIL_SUBJECT.safe_substitute(template_data),
                body=self.EMAIL_BODY.safe_substitute(template_data),
            )
        
        elif channel == NotificationChannel.SLACK:
            return TemplateResult(
                subject=f"{template_data['emoji']} Order Filled: {template_data['symbol']}",
                body=self.SLACK_BODY.safe_substitute(template_data),
            )
        
        elif channel == NotificationChannel.SMS:
            body = self.SMS_BODY.safe_substitute(template_data)
            return TemplateResult(
                subject="Trade Alert",
                body=body[:160],
            )
        
        else:  # PUSH
            return TemplateResult(
                subject=f"{template_data['symbol']} Order Filled",
                body=f"{template_data['side']} {template_data['quantity']} @ ${template_data['fill_price']}",
            )


class OrderCreatedTemplate(NotificationTemplate):
    """Template for order created notifications."""
    
    notification_type = NotificationType.ORDER_CREATED
    
    EMAIL_SUBJECT = Template("Order Created: $symbol")
    EMAIL_BODY = Template("""
Your order has been created and is pending execution.

Order Details:
- Order ID: $order_id
- Symbol: $symbol
- Side: $side
- Quantity: $quantity shares
- Order Type: $order_type
- Limit Price: $$limit_price

We will notify you when the order is filled.
""".strip())
    
    def render(
        self,
        channel: NotificationChannel,
        data: dict[str, Any],
    ) -> TemplateResult:
        """Render order created notification."""
        
        template_data = {
            "order_id": self._safe_get(data, "order_id"),
            "symbol": self._safe_get(data, "symbol"),
            "side": self._safe_get(data, "side", "unknown"),
            "quantity": self._safe_get(data, "quantity", 0),
            "order_type": self._safe_get(data, "order_type", "market"),
            "limit_price": self._safe_get(data, "limit_price", "N/A"),
        }
        
        if channel == NotificationChannel.EMAIL:
            return TemplateResult(
                subject=self.EMAIL_SUBJECT.safe_substitute(template_data),
                body=self.EMAIL_BODY.safe_substitute(template_data),
            )
        
        return TemplateResult(
            subject=f"📋 New Order: {template_data['symbol']}",
            body=f"{template_data['side']} {template_data['quantity']} {template_data['symbol']}",
        )


class OrderCancelledTemplate(NotificationTemplate):
    """Template for order cancelled notifications."""
    
    notification_type = NotificationType.ORDER_CANCELLED
    
    EMAIL_SUBJECT = Template("Order Cancelled: $symbol")
    EMAIL_BODY = Template("""
Your order has been cancelled.

Order Details:
- Order ID: $order_id
- Symbol: $symbol
- Reason: $reason

If you did not request this cancellation, please contact support.
""".strip())
    
    def render(
        self,
        channel: NotificationChannel,
        data: dict[str, Any],
    ) -> TemplateResult:
        """Render order cancelled notification."""
        
        template_data = {
            "order_id": self._safe_get(data, "order_id"),
            "symbol": self._safe_get(data, "symbol"),
            "reason": self._safe_get(data, "reason", "No reason provided"),
        }
        
        if channel == NotificationChannel.EMAIL:
            return TemplateResult(
                subject=self.EMAIL_SUBJECT.safe_substitute(template_data),
                body=self.EMAIL_BODY.safe_substitute(template_data),
            )
        
        return TemplateResult(
            subject=f"❌ Order Cancelled: {template_data['symbol']}",
            body=f"Order {template_data['order_id']} cancelled: {template_data['reason']}",
        )


class TemplateRegistry:
    """
    Registry of notification templates.
    
    Maps NotificationType to the appropriate template class.
    """
    
    def __init__(self) -> None:
        """Initialize with default templates."""
        self._templates: dict[NotificationType, NotificationTemplate] = {}
        self._register_defaults()
    
    def _register_defaults(self) -> None:
        """Register default templates."""
        self.register(OrderFilledTemplate())
        self.register(OrderCreatedTemplate())
        self.register(OrderCancelledTemplate())
    
    def register(self, template: NotificationTemplate) -> None:
        """Register a template."""
        self._templates[template.notification_type] = template
    
    def get_template(self, notification_type: NotificationType) -> NotificationTemplate | None:
        """Get template for notification type."""
        return self._templates.get(notification_type)