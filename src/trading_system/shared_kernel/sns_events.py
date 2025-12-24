"""
SNS-publishable domain events.

These events implement the Publishable protocol for SNS publishing.
Each event has:
- event_type property (for SNS message filtering)
- to_dict() method (for JSON serialization)

Use these for events that need to be published across service boundaries.
"""

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from uuid import uuid4


@dataclass
class PriceUpdatedEvent:
    """Event published when a stock price updates."""

    symbol: str
    price: Decimal
    timestamp: datetime
    source: str
    event_id: UUID = field(default_factory=uuid4)

    @property
    def event_type(self) -> str:
        """Return event type name for SNS filtering."""
        return self.__class__.__name__

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "symbol": self.symbol,
            "price": str(self.price),
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }


@dataclass
class OrderCreatedEvent:
    """Event published when a new order is created."""

    order_id: UUID
    symbol: str
    side: str  # "buy" or "sell"
    quantity: int
    order_type: str  # "market", "limit"
    price: Decimal | None = None  # Only for limit orders
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_type(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "order_id": str(self.order_id),
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "price": str(self.price) if self.price else None,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OrderFilledEvent:
    """Event published when an order is executed."""

    order_id: UUID
    symbol: str
    side: str
    quantity: int
    fill_price: Decimal
    commission: Decimal = Decimal("0")
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_type(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "order_id": str(self.order_id),
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "fill_price": str(self.fill_price),
            "commission": str(self.commission),
            "timestamp": self.timestamp.isoformat(),
        }