"""
Order Entity - Represents a trading order with lifecycle.

Key differences from Value Objects:
1. Has unique identity (ID)
2. Mutable - state change over time
3. Has lifecycle (PENDING -> SUBMITTED -> FILLED)
"""


from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from trading_system.domain.value_objects.price import Price
from trading_system.domain.value_objects.symbol import Symbol


# Enums fro type safety and clarity
class OrderType(Enum):
    """
    Types of orders in our system.
    Using Enum provides type safety and prevents typos.
    """
    MARKET = "MARKET"           # Execute immediately at current price
    LIMIT = "LIMIT"             # Execute at specific price or better
    STOP = "STOP"               # Trigger when price reaches level
    STOP_LIMIT = "STOP_LIMIT"   # Stop that becomes limit order


class OrderSide(Enum):
    """ Whether we're buying or selling """
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    """
    Order lifescycle states.
    Orders transition through these states.
    """
    PENDING = "PENDING"         # Created but not sent
    SUBMITTED = "SUBMITTED"     # Sent to exchange
    FILLED = "FILLED"           # Completely executede
    CANCELLED = "CANCELLED"     # Cancelled by user
    REJECTED = "REJECTED"       # Rejected by exchange


@dataclass
class Order:
    """
    Order entity - mutable domain object with identity

    Why @dataclass without frozen=True?
    - Entities are mutable (state changes)
    - Still reduces boilerplate code
    - Provides nice __repr__ for debugging

    Why use field(default_factory=...)?
    - For mutable defaults (like uuid4())
    - Prevents sharing default values between instances
    """

    # Required fields (no defaults)
    symbol: Symbol
    quantity: int
    side: OrderSide
    order_type: OrderType

    # Optional fields (with defaults)
    limit_price: Optional[Price] = None
    stop_price: Optional[Price] = None

    # Identity and state
    # field(default_factory=uuid4) creates new UUID for each instance
    # Why? Can't use uuid4() directly as default (would share same ID!)
    id: UUID = field(default_factory=uuid4)
    status: OrderStatus = OrderStatus.PENDING

    # Execution details
    fill_price: Optional[Price] = None
    filled_quantity: int = 0

    # Timestamps
    # lambda: datetime.now(timezone.utc) creates current time for each instance
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """ Validate order parameters after initialization """
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")
        
        # Limit orders must have limit price
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("Limit order requires limit_price")
        
        # Stop orders must have stop price
        if self.order_type == OrderType.STOP and self.stop_price is None:
            raise ValueError("Stop order requires stop_price")
        
    # Factory methods - cleaner way to create spefic order types
    @classmethod    # Can be called on class, not instance
    def create_market_order(
        cls,        # cls refers to the class (Order)
        symbol: Symbol,
        quantity: int,
        side: OrderSide
    ) -> 'Order':
        """
        Factory method for creating market orders.

        Why use factory methods?
        - Cleaner intent than constructor with many parameters
        - Can have multiple ways to create objects
        - Encapsulates creation logic

        @classmethod vs @staticmethod:
        - @classmethod receives the class at first parameter
        - Can create instances of the class
        - @staticmethod doesn't receive class, just utility function
        """
        return cls(
            symbol=symbol,
            quantity=quantity,
            side=side,
            order_type=OrderType.MARKET
        )
    
    @classmethod
    def create_limit_order(
        cls,
        symbol: Symbol,
        quantity: int,
        side: OrderSide,
        limit_price: Price
    ) -> 'Order':
        """ Factory method for creating limit orders """
        return cls(
            symbol=symbol,
            quantity=quantity,
            side=side,
            order_type=OrderType.LIMIT,
            limit_price=limit_price
        )

    # Business methods - these change the entity's state
    def submit(self) -> None:
        """
        Submit order for execution.

        Why void return (-> None)?
        - This method changes state, doesn't return value
        - Makes intent clear
        """
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"Cannot submit order in {self.status} status")
        
        self.status = OrderStatus.SUBMITTED
        self.submitted_at = datetime.now(timezone.utc)

    def fill(self, price: Price, quantity: Optional[int] = None) -> None:
        """
        Mark order as filled.

        Optional[int] = None means parameter is optional with None default.
        """
        if self.status != OrderStatus.SUBMITTED:
            raise ValueError(f"Cannot fill order in {self.status} status")

        self.fill_price = price
        self.filled_quantity = quantity or self.quantity
        self.status = OrderStatus.FILLED
        self.filled_at = datetime.now(timezone.utc)

    def cancel(self) -> None:
        """ Cancel the order """
        if self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            raise ValueError(f"Cannot cancel order in {self.status} status")

        self.status = OrderStatus.CANCELLED

    @property
    def remaining_quantity(self) -> int:
        """ Calculate how much is left to fill """
        return self.quantity - self.filled_quantity
    
    # Special methods for Python integration
    def __eq__(self, other: object) -> bool:
        """ 
        Define euality for entities (based on ID)
        
        Why override __eq__?
        - Entities are equal if they have the same identity
        - Not based on attributes like value objects
        """
        if not isinstance(other, Order):
            return False

        return self.id == other.id

    def __hash__(self) -> int:
        """
        Make orders hashable (can be used in sets/dicts).

        Why override __hash__?
        - Needed for sets and dictionary keys
        - Must be consistent with __eq__
        """
        return hash(self.id)
    
    def __repr__(self) -> str:
        """
        Developer-friendly string representation.
        Useful for debugging.
        """
        return (
            f"Order(id={self.id!r}, symbol={self.symbol}, " 
            f"Quantity={self.quantity}, status={self.status})"
        )
    

    
