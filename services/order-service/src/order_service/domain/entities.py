"""
Order Domain Entities.

Core business objects for the Order Management Service.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
import uuid


class OrderSide(str, Enum):
    """
    Order side (buy or sell).
    
    Using (str, Enum) for automatic JSON serialization.
    The string value is used when converting to JSON.
    """
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """
    Order lifecycle status.
    
    State Transitions:
    ══════════════════
    
    ┌──────────────────────────────────────────────────────────────────────────┐
    │                         CANCELLED (user decides)                         │
    │  User explicitly requests cancellation before order is fully filled.     │
    └──────────────────────────────────────────────────────────────────────────┘
       ▲          ▲            ▲              ▲              ▲              ▲
       │          │            │              │              │              │
    PENDING → VALIDATED → RISK_CHECKED → FUNDS_RESERVED → SUBMITTED → PARTIALLY_FILLED → FILLED
       │          │            │              │              │              │
       ▼          ▼            ▼              ▼              ▼              ▼
    ┌──────────────────────────────────────────────────────────────────────────┐
    │                         REJECTED (system decides)                        │
    │  Invalid symbol, risk limit exceeded, insufficient funds, broker error   │
    └──────────────────────────────────────────────────────────────────────────┘
    
    TERMINAL STATES (no further transitions):
    • FILLED     - Order fully executed
    • CANCELLED  - User cancelled before completion
    • REJECTED   - System/broker refused the order
    
    NOTE ON PYLINT: Pylint doesn't recognize methods on Enum subclasses well,
    especially with multiple inheritance (str, Enum). You may see E1101 errors
    like "Instance of 'OrderStatus' has no 'is_terminal' member". This is a
    false positive - the methods work correctly at runtime. Add this to your
    pyproject.toml to suppress:
    
        [tool.pylint.messages_control]
        disable = ["no-member"]  # For Enum method false positives
    
    Or use inline: # pylint: disable=no-member
    """
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    RISK_CHECKED = "RISK_CHECKED"
    FUNDS_RESERVED = "FUNDS_RESERVED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    
    def is_terminal(self) -> bool:
        """Check if this is a final status."""
        return self in (
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED
        )
    
    def can_cancel(self) -> bool:
        """Check if order can be cancelled from this status."""
        return self in (
            OrderStatus.PENDING,
            OrderStatus.VALIDATED,
            OrderStatus.RISK_CHECKED,
            OrderStatus.FUNDS_RESERVED,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED  # Can cancel unfilled portion
        )


@dataclass
class Order:
    """
    Order aggregate root.
    
    Represents a trading order with full lifecycle tracking.
    """
    
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Order details
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: Decimal = Decimal("0")
    
    # Price (for limit/stop orders)
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    
    # Execution details
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Optional[Decimal] = None
    
    # Status tracking
    status: OrderStatus = OrderStatus.PENDING
    status_history: list[tuple[OrderStatus, datetime]] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    
    # Financial
    estimated_value: Optional[Decimal] = None
    reserved_funds: Optional[Decimal] = None
    commission: Decimal = Decimal("0")
    
    # Metadata
    account_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Saga tracking
    saga_id: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Record initial status in history."""
        if not self.status_history:
            self.status_history.append((self.status, self.created_at))
    
    def transition_to(
        self, 
        new_status: OrderStatus, 
        reason: Optional[str] = None
    ) -> None:
        """
        Transition order to new status with validation.
        
        Args:
            new_status: Target status
            reason: Rejection/cancellation reason (if applicable)
            
        Raises:
            ValueError: If transition is not allowed
        """
        # Define valid transitions
        valid_transitions: dict[OrderStatus, set[OrderStatus]] = {
            OrderStatus.PENDING: {
                OrderStatus.VALIDATED, 
                OrderStatus.REJECTED,
                OrderStatus.CANCELLED
            },
            OrderStatus.VALIDATED: {
                OrderStatus.RISK_CHECKED, 
                OrderStatus.REJECTED,
                OrderStatus.CANCELLED
            },
            OrderStatus.RISK_CHECKED: {
                OrderStatus.FUNDS_RESERVED, 
                OrderStatus.REJECTED,
                OrderStatus.CANCELLED
            },
            OrderStatus.FUNDS_RESERVED: {
                OrderStatus.SUBMITTED, 
                OrderStatus.REJECTED,
                OrderStatus.CANCELLED
            },
            OrderStatus.SUBMITTED: {
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED, 
                OrderStatus.REJECTED,
                OrderStatus.CANCELLED
            },
            OrderStatus.PARTIALLY_FILLED: {
                OrderStatus.FILLED,
                OrderStatus.CANCELLED
            }
        }
        
        if self.status.is_terminal():  # pylint: disable=no-member
            raise ValueError(f"Cannot transition from terminal status {self.status}")
        
        allowed = valid_transitions.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {self.status} → {new_status}. "
                f"Allowed: {allowed}"
            )
        
        # Perform transition
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self.status_history.append((new_status, self.updated_at))
        
        if reason and new_status in (OrderStatus.REJECTED, OrderStatus.CANCELLED):
            self.rejection_reason = reason
    
    @property
    def remaining_quantity(self) -> Decimal:
        """Calculate unfilled quantity."""
        return self.quantity - self.filled_quantity
    
    @property
    def is_complete(self) -> bool:
        """Check if order is fully processed."""
        return self.status.is_terminal()  # pylint: disable=no-member
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": str(self.quantity),
            "limit_price": str(self.limit_price) if self.limit_price else None,
            "filled_quantity": str(self.filled_quantity),
            "average_fill_price": str(self.average_fill_price) if self.average_fill_price else None,
            "status": self.status.value,
            "rejection_reason": self.rejection_reason,
            "estimated_value": str(self.estimated_value) if self.estimated_value else None,
            "account_id": self.account_id,
            "saga_id": self.saga_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }