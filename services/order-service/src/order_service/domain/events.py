"""
Order Domain Events.

Events published by the Order Service for other services to consume.
These are integration events that cross service boundaries.

NOTE: We use str for numeric fields (quantity, price) because:
1. JSON doesn't support Decimal natively
2. Avoids floating-point precision issues in serialization
3. Each consumer can parse to their preferred numeric type
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class OrderEvent:
    """Base class for order-related events."""
    
    order_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_type(self) -> str:
        """Return the event class name as the type."""
        return self.__class__.__name__
    
    def to_dict(self) -> dict:
        """Convert to dictinoary for serialization."""
        return {
            "event_type": self.event_type,
            "order_id": self.order_id,
            "timestamp": self.timestamp.isoformat()
        }
    

@dataclass
class OrderCreatedEvent(OrderEvent):
    """Emitted when a new order is created and saga starts."""

    symbol: str = ""
    side: str = ""
    order_type: str = ""
    quantity: str = "0"
    account_id: str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "account_id": self.account_id
        })
        return base
    

@dataclass
class OrderValidatedEvent(OrderEvent):
    """Emitted when order passes validation."""

    estimated_value: Optional[str] = None

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({"estimated_value": self.estimated_value})
        return base
    

@dataclass
class OrderFilledEvent(OrderEvent):
    """Emitted when an order is filled (partially or fully)."""
    
    symbol: str = ""
    filled_quantity: str = "0"
    fill_price: str = "0"
    total_filled: str = "0"
    remaining_quantity: str = "0"
    broker_order_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "symbol": self.symbol,
            "filled_quantity": self.filled_quantity,
            "fill_price": self.fill_price,
            "total_filled": self.total_filled,
            "remaining_quantity": self.remaining_quantity,
            "broker_order_id": self.broker_order_id
        })
        return base


@dataclass
class OrderFailedEvent(OrderEvent):
    """Emitted when an order fails at any saga step."""
    
    reason: str = ""
    failed_at_step: str = ""
    was_compensated: bool = False
    
    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "reason": self.reason,
            "failed_at_step": self.failed_at_step,
            "was_compensated": self.was_compensated
        })
        return base


@dataclass
class OrderCancelledEvent(OrderEvent):
    """Emitted when an order is cancelled."""
    
    reason: str = ""
    cancelled_by: str = ""  # "user", "saga_compensation", "system"
    filled_before_cancel: str = "0"
    
    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "reason": self.reason,
            "cancelled_by": self.cancelled_by,
            "filled_before_cancel": self.filled_before_cancel
        })
        return base

