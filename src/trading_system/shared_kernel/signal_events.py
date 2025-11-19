# src/trading_system/shared_kernel/signal_events.py
"""
Signal Events for Trading Strategies.

Events published when trading strategies generate buy/sell signals.
These events are optimized for event sourcing with a flat structure.

CORRECTED VERSION:
- Uses SignalType enum for type safety
- Removed unnecessary _validated flag
- Fixed from_dict to not pass version parameter
- Clarified **super().to_dict() usage
- Uses create() factory method for clean event creation
"""

from dataclasses import dataclass, field
from typing import ClassVar
from decimal import Decimal
from datetime import datetime

from trading_system.shared_kernel.base_event import BaseEvent
from trading_system.strategies.signals import SignalType  # Import enum for type safety


@dataclass(frozen=True)
class SignalGeneratedEvent(BaseEvent):
    """
    Event published when a trading strategy generates a signal.
    
    This is a flattened version optimized for event sourcing.
    All signal data is at the top level for easy querying and storage.
    
    PYTHON FEATURES DEMONSTRATED:
    1. @dataclass(frozen=True) - Immutable event (can't change after creation)
    2. field(default_factory=...) - Default values for mutable types
    3. ClassVar - Class-level variable (shared across all instances)
    4. Enum usage - Type-safe signal types
    5. __post_init__ - Validation after initialization
    6. @classmethod - Alternative constructor pattern
    7. **dict unpacking - Merging parent and child dictionaries
    
    METADATA FIELDS EXPLAINED:
    - aggregate_type: Instance variable, tells us which domain object type (Strategy, Order, etc.)
                      Stored in each event, used for categorizing and querying
    - event_name: ClassVar (class variable), identifies this event class ("signal_generated")
                  Shared by all instances, not stored per event, used for routing/deserialization
    
    Example using factory method (RECOMMENDED):
        event = SignalGeneratedEvent.create(
            aggregate_id="strategy-ma-AAPL",
            aggregate_type="Strategy",
            strategy_name="MovingAverageCrossover",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            signal_strength=0.85,
            price=Decimal("150.25"),
            indicators={"fast_ma": 150.45, "slow_ma": 149.80},
            reason="Fast MA crossed above Slow MA"
        )
        # event_id, occurred_at, version automatically set!
    
    Example direct construction (when you need control):
        event = SignalGeneratedEvent(
            event_id=str(uuid.uuid4()),
            occurred_at=datetime.utcnow(),
            aggregate_id="strategy-ma-AAPL",
            aggregate_type="Strategy",
            version=0,
            strategy_name="MovingAverageCrossover",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            signal_strength=0.85,
            price=Decimal("150.25"),
            indicators={"fast_ma": 150.45, "slow_ma": 149.80},
            reason="Fast MA crossed above Slow MA"
        )
    """
    
    # Strategy identification
    strategy_name: str      # Which strategy generated this?
    symbol: str             # Which stock/asset?
    
    # Signal details - CORRECTED: Now using enum
    signal_type: SignalType  # Type-safe: BUY, SELL, or HOLD
    signal_strength: float  # 0.0 to 1.0 (granular confidence level)
    
    # Market context
    price: Decimal  # Current price
    
    # Technical analysis
    indicators: dict  # All indicator values
    
    # Human explanation
    reason: str  # Why this signal?
    
    # Event sourcing metadata (must be defined as fields with defaults)
    aggregate_type: str = "Strategy"  # Categorizes this as a Strategy event
    version: int = 0  # Event version (Event Store will set actual value)
    
    # event_name: Class variable (ClassVar) - identifies the event class type
    # Shared across all instances, NOT stored per event (saves space)
    # Used for event routing and deserialization: "signal_generated" → SignalGeneratedEvent
    event_name: ClassVar[str] = "signal_generated"
    
    @classmethod
    def create(
        cls,
        strategy_name: str,
        symbol: str,
        signal_type: SignalType,
        signal_strength: float,
        price: Decimal,
        indicators: dict = None,
        reason: str = "",
        **kwargs
    ) -> 'SignalGeneratedEvent':
        """
        Factory method to create SignalGeneratedEvent with sensible defaults.
        
        PATTERN EXPLANATION:
        This method:
        1. Sets aggregate_id automatically (strategy-{name}-{symbol})
        2. Sets aggregate_type to "Strategy"
        3. Calls parent create() which sets event_id, occurred_at, version
        4. Validates inputs
        
        Why use this instead of direct construction?
        - Less verbose (no need to specify event_id, occurred_at, etc.)
        - Automatic aggregate_id generation
        - Consistent pattern across all events
        - Easy to add validation or logic later
        
        Args:
            strategy_name: Name of the strategy
            symbol: Trading symbol (e.g., "AAPL")
            signal_type: BUY, SELL, or HOLD (enum)
            signal_strength: Confidence level (0.0 to 1.0)
            price: Current market price
            indicators: Technical indicator values (optional)
            reason: Human-readable explanation (optional)
            **kwargs: Additional fields or overrides
        
        Returns:
            New SignalGeneratedEvent instance
        
        Example:
            event = SignalGeneratedEvent.create(
                strategy_name="MovingAverage",
                symbol="AAPL",
                signal_type=SignalType.BUY,
                signal_strength=0.85,
                price=Decimal("150.25"),
                indicators={"fast_ma": 150.45, "slow_ma": 149.80},
                reason="Fast MA crossed above Slow MA"
            )
        """
        # Automatic aggregate_id generation
        aggregate_id = kwargs.pop('aggregate_id', f"strategy-{strategy_name}-{symbol}")
        
        # Call parent factory method
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type="Strategy",  # This is a Strategy-related event
            strategy_name=strategy_name,
            symbol=symbol,
            signal_type=signal_type,
            signal_strength=signal_strength,
            price=price,
            indicators=indicators or {},
            reason=reason,
            **kwargs
        )
    
    def __post_init__(self):
        """
        Validate signal data.
        
        PYTHON FEATURE: __post_init__
        Called automatically after __init__ completes in dataclasses.
        Perfect for validation and computed fields.
        
        CORRECTED: Removed unnecessary object.__setattr__(self, '_validated', True)
        That line served no purpose - there's no _validated field in BaseEvent.
        """
        if not self.strategy_name:
            raise ValueError("strategy_name is required")
        if not self.symbol:
            raise ValueError("symbol is required")
        # Type checking - ensure it's the enum type
        if not isinstance(self.signal_type, SignalType):
            raise TypeError(f"signal_type must be SignalType enum, got {type(self.signal_type)}")
        if not 0.0 <= self.signal_strength <= 1.0:
            raise ValueError(f"signal_strength must be 0.0-1.0, got {self.signal_strength}")
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary for serialization.
        
        PYTHON FEATURE: **super().to_dict()
        The ** operator "unpacks" a dictionary into key-value pairs.
        
        Example:
            parent_dict = {"a": 1, "b": 2}
            child_dict = {**parent_dict, "c": 3}
            # Result: {"a": 1, "b": 2, "c": 3}
        
        In our case:
            super().to_dict() returns:
            {
                "event_id": "evt-123",
                "occurred_at": "2024-03-15T10:30:00",
                "aggregate_id": "strategy-ma-AAPL",
                "aggregate_type": "Strategy",
                "version": 1,
                "event_type": "SignalGeneratedEvent"
            }
            
            We add:
            {
                "strategy_name": "MovingAverage",
                "symbol": "AAPL",
                "signal_type": "BUY",
                ...
            }
            
            Result: All fields merged into one dictionary!
        
        Why this pattern?
        - DRY: Don't repeat parent's serialization logic
        - Maintainable: If parent adds fields, automatically included
        - Clean inheritance: Each class handles its own fields
        """
        return {
            **super().to_dict(),  # Unpack parent's fields
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,  # Convert enum to string for JSON
            "signal_strength": self.signal_strength,
            "price": str(self.price),  # Decimal → string for JSON
            "indicators": self.indicators,
            "reason": self.reason,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SignalGeneratedEvent":
        """
        Reconstruct event from dictionary.
        
        PYTHON FEATURE: @classmethod
        Method that receives the class as first argument (cls), not instance.
        Used for alternative constructors.
        
        IMPORTANT: Only pass fields that BaseEvent constructor expects.
        - BaseEvent has: event_id, aggregate_id, occurred_at (3 fields)
        - aggregate_type and version are defined in SignalGeneratedEvent with defaults
        - They don't need to be passed - dataclass will use the default values
        
        FIX EXPLAINED:
        ❌ Wrong: Passing aggregate_type and version causes Pylint error
        ✓ Right: Don't pass them - they have defaults in the dataclass definition
        """
        # Convert string back to enum
        signal_type_str = data.get("signal_type", "HOLD")
        signal_type = SignalType(signal_type_str)  # String → Enum
        
        # Convert string back to Decimal
        price_str = data.get("price", "0")
        price = Decimal(price_str)
        
        return cls(
            # BaseEvent fields (required)
            event_id=data["event_id"],
            aggregate_id=data["aggregate_id"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            # SignalGeneratedEvent fields
            strategy_name=data.get("strategy_name", ""),
            symbol=data.get("symbol", ""),
            signal_type=signal_type,
            signal_strength=data.get("signal_strength", 0.0),
            price=price,
            indicators=data.get("indicators", {}),
            reason=data.get("reason", ""),
            # aggregate_type and version NOT passed - they use defaults from dataclass
        )