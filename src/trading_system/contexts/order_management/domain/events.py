"""
Domain Events for Order Management.

This file demonstrates Domain-Driven Design (DDD) concepts:
- Domain Events capture things that happened in the business domain
- Events are immutable (using frozen=True)
- Events carry all necessary data for downstream processing

Events vs Commands:
- Command: "Please create an order" (can be rejected)
- Event: "An order was created" (already happened, fact)

Event Naming:
- Past tense: OrderCreated, not CreateOrder
- Domain language: OrderFilled, not DatabaseUpdated
- Specific: OrderPartiallyFilled, not OrderUpdated
"""

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import ClassVar, Optional, Dict, Any
from enum import Enum

from trading_system.shared_kernel.events import BaseEvent


# ============================================
# ENUMS FOR DOMAIN CONCEPTS
# ============================================

class OrderType(Enum):
    """
    Enum for order types.
    
    Enums in Python:
    - Provide type safety (can't use invalid values)
    - Self-documenting (IDE autocomplete)
    - Prevent typos ('MARKET' vs 'MARKT')
    - Easy to iterate: for order_type in OrderType
    - Comparable: OrderType.MARKET == OrderType.MARKET
    
    Why not just strings?
    order_type = "MARKET"  # Could typo as "MARKT"
    order_type = "INVALID"  # No compile-time checking
    
    With Enum:
    order_type = OrderType.MARKET  # Type-safe
    order_type = OrderType.INVALID  # Error: no such member
    """
    MARKET = "MARKET"  # Execute at current market price
    LIMIT = "LIMIT"    # Execute at specific price or better
    STOP = "STOP"      # Trigger when price crosses threshold
    STOP_LIMIT = "STOP_LIMIT"  # Stop that becomes limit order


class OrderStatus(Enum):
    """
    Order lifecycle states.
    
    State machine for orders:
    PENDING -> VALIDATED -> SUBMITTED -> FILLED
                |                |-> PARTIALLY_FILLED -> FILLED
                |-> REJECTED     |-> CANCELLED
    """
    PENDING = "PENDING"              # Just created, not validated yet
    VALIDATED = "VALIDATED"          # Passed validation checks
    REJECTED = "REJECTED"            # Failed validation or risk checks
    SUBMITTED = "SUBMITTED"          # Sent to exchange
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Some quantity executed
    FILLED = "FILLED"                # Fully executed
    CANCELLED = "CANCELLED"          # Cancelled by user or system


class OrderSide(Enum):
    """Buy or Sell side."""
    BUY = "BUY"    # Long position
    SELL = "SELL"  # Short position


# ============================================
# ORDER DOMAIN EVENTS
# ============================================

@dataclass(frozen=True)  # frozen=True makes ALL fields immutable after creation
class OrderCreatedEvent(BaseEvent):
    """
    Event raised when a new order is created.
    
    frozen=True implications:
    1. All fields become read-only after __init__
    2. Instance can be used as dict key or in set
    3. __hash__ is automatically generated
    4. Attempting to modify raises FrozenInstanceError
    
    Why immutable events?
    - Events are historical facts (can't change the past)
    - Thread-safe (no locks needed)
    - Safe to share between components
    - Can be cached safely
    
    Example of immutability:
    event = OrderCreatedEvent(...)
    event.quantity = 200  # Raises FrozenInstanceError!
    
    Note: All fields must be provided - no defaults to avoid dataclass inheritance issues
    """
    
    # ClassVar: Class variable, shared by all instances
    # Not included in __init__, __repr__, __eq__, etc.
    # Access via: OrderCreatedEvent.event_type or instance.event_type
    event_type: ClassVar[str] = "order.created"
    
    # Instance fields with type annotations
    # Type hints are not enforced at runtime but help with:
    # 1. IDE autocomplete and error detection
    # 2. Static type checking with mypy
    # 3. Documentation for other developers
    
    # Required fields - no defaults to avoid dataclass ordering issues
    order_id: str
    symbol: str  # Stock ticker symbol (AAPL, GOOGL, etc.)
    quantity: Decimal  # Use Decimal for financial precision
    price: Decimal  # Use Decimal for financial precision
    order_type: OrderType  # Must be explicitly provided
    side: OrderSide  # Must be explicitly provided
    account_id: Optional[str]  # Can be None
    metadata: Dict[str, Any]  # Should be provided (empty dict if nothing)
    
    @property  # Makes this a computed property, not stored field
    def notional_value(self) -> Decimal:
        """
        Calculate notional value of the order.
        
        @property decorator:
        - Access like attribute: event.notional_value (no parentheses!)
        - Computed on-the-fly, not stored
        - Read-only by default (no setter defined)
        - Can add setter with @notional_value.setter if needed
        
        Without @property:
        def get_notional_value(self):  # Must call with ()
            return self.quantity * self.price
        value = event.get_notional_value()  # Method syntax
        
        With @property:
        value = event.notional_value  # Attribute syntax, cleaner!
        """
        return self.quantity * self.price
    
    def to_message(self) -> dict:
        """
        Serialize for message queue (SQS/Kafka).
        
        Why serialize to dict?
        1. SQS needs JSON or string messages
        2. Databases store JSON
        3. REST APIs return JSON
        4. Easy migration between message systems (SQS -> Kafka)
        
        Note: Decimal and Enum need special handling
        - Decimal -> str (to preserve precision)
        - Enum -> value (to get string value)
        """
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'order_id': self.order_id,
            'symbol': self.symbol,
            'quantity': str(self.quantity),  # Decimal to string
            'price': str(self.price),
            'order_type': self.order_type.value,  # Enum to string
            'side': self.side.value,
            'account_id': self.account_id,
            'timestamp': self.timestamp.isoformat(),  # datetime to ISO string
            'metadata': self.metadata,
            'version': self.version
        }
    
    @classmethod  # Receives class, not instance
    def from_message(cls, data: dict) -> 'OrderCreatedEvent':
        """
        Deserialize from message queue.
        
        @classmethod vs @staticmethod:
        
        @classmethod:
        - First arg is the class itself (cls)
        - Can create instances of the class
        - Can access class variables
        - Used for alternative constructors (factory pattern)
        
        @staticmethod:
        - No implicit first argument
        - Just a regular function inside the class
        - Can't access class or instance state
        - Used for utility functions
        
        Example usage:
        event = OrderCreatedEvent.from_message(data)
        
        Note: For frozen dataclass with inheritance, we need to use a workaround
        to properly construct the instance with all fields.
        """
        # Extract and prepare the fields
        import uuid
        
        # Prepare BaseEvent fields with defaults
        event_id = data.get('event_id', str(uuid.uuid4()))
        timestamp = data.get('timestamp')
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.utcnow()
        version = data.get('version', 1)
        
        # Prepare OrderCreatedEvent fields
        order_id = data['order_id']
        symbol = data['symbol']
        quantity = Decimal(data['quantity']) if isinstance(data['quantity'], str) else data['quantity']
        price = Decimal(data['price']) if isinstance(data['price'], str) else data['price']
        
        # Handle enums
        order_type = data.get('order_type', OrderType.LIMIT.value)
        if isinstance(order_type, str):
            order_type = OrderType(order_type)
        
        side = data.get('side', OrderSide.BUY.value)
        if isinstance(side, str):
            side = OrderSide(side)
        
        account_id = data.get('account_id')
        metadata = data.get('metadata', {})
        
        # Create instance using object.__new__ to bypass frozen __init__ issues
        instance = object.__new__(cls)
        
        # Set all fields using object.__setattr__ (required for frozen dataclass)
        # Set parent class fields first
        object.__setattr__(instance, 'event_id', event_id)
        object.__setattr__(instance, 'timestamp', timestamp)
        object.__setattr__(instance, 'version', version)
        
        # Set this class's fields
        object.__setattr__(instance, 'order_id', order_id)
        object.__setattr__(instance, 'symbol', symbol)
        object.__setattr__(instance, 'quantity', quantity)
        object.__setattr__(instance, 'price', price)
        object.__setattr__(instance, 'order_type', order_type)
        object.__setattr__(instance, 'side', side)
        object.__setattr__(instance, 'account_id', account_id)
        object.__setattr__(instance, 'metadata', metadata)
        
        return instance
    
    def _get_payload(self) -> dict:
        """
        Override base class method to provide event-specific data.
        
        Leading underscore (_) convention:
        - "Internal" or "protected" method
        - Not part of public API
        - Can be overridden by subclasses
        - Users shouldn't call directly
        
        Python doesn't enforce privacy (no true private methods)
        This is just a convention to indicate intent
        """
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'quantity': str(self.quantity),
            'price': str(self.price),
            'order_type': self.order_type.value,
            'side': self.side.value,
            'account_id': self.account_id,
            'notional_value': str(self.notional_value),  # Include computed property
            'metadata': self.metadata
        }


@dataclass(frozen=True)
class OrderValidatedEvent(BaseEvent):
    """Event raised when order passes validation."""
    
    event_type: ClassVar[str] = "order.validated"
    
    order_id: str
    validation_status: str
    validation_messages: list  # Must be provided (empty list if no messages)
    
    @property
    def is_valid(self) -> bool:
        """
        Check if validation passed.
        
        Computed property for convenience.
        Makes code more readable:
        if event.is_valid: instead of if event.validation_status == "PASSED":
        """
        return self.validation_status == "PASSED"


@dataclass(frozen=True)
class OrderRejectedEvent(BaseEvent):
    """Event raised when order is rejected."""
    
    event_type: ClassVar[str] = "order.rejected"
    
    order_id: str
    reason: str
    rejection_code: Optional[str]  # Can be None
    details: Dict[str, Any]  # Must be provided (empty dict if no details)