# src/trading_system/shared_kernel/events.py
"""
Base Event Class with Event Sourcing support.

Updated for Day 7 to support PostgreSQL event store.

DESIGN PATTERN: Factory Method
Instead of using default_factory in dataclass fields, we use a create() 
class method. This gives us:
1. Explicit control over defaults
2. Easy validation
3. Clear API for event creation
4. Better inheritance patterns
"""

from dataclasses import dataclass, field, asdict
from typing import ClassVar, Optional
from datetime import datetime
from decimal import Decimal
import uuid


@dataclass(frozen=True)
class BaseEvent:
    """
    Base class for all domain events.
    
    PYTHON FEATURE: frozen=True
    Makes instances immutable (no attribute assignment after creation).
    Critical for events - they're historical facts that can't change!
    
    DESIGN PATTERN: No Default Values
    We don't use field(default_factory=...) because:
    - Makes inheritance cleaner (child classes don't override defaults)
    - Forces explicit event creation (no accidental empty events)
    - Works better with factory method pattern
    
    NEW FOR EVENT SOURCING:
    - aggregate_type: Type of aggregate (Strategy, Backtest, etc.)
    - version: Event version within aggregate's stream
    - event_name: ClassVar for event routing
    - create(): Factory method for convenient event creation
    - from_dict(): Deserialize from database
    """
    
    # Core event metadata
    event_id: str
    occurred_at: datetime
    
    # Aggregate relationship
    aggregate_id: str  # Which aggregate? e.g., "strategy-ma-AAPL"
    aggregate_type: str  # What type? e.g., "Strategy", "Backtest", "Order"
    
    # Version for event sourcing (set by event store, not during construction)
    # Used for optimistic concurrency control - ensures events are applied in correct order
    version: int
    
    # Python class variable (not instance variable) - shared across all instances
    # Subclasses override this to identify their event type
    event_name: ClassVar[str] = "base_event"
    
    @classmethod
    def create(
        cls, 
        aggregate_id: str, 
        aggregate_type: str = "",
        **kwargs
    ) -> 'BaseEvent':
        """
        Factory method to create events with sensible defaults.
        
        PATTERN: Factory Method (Gang of Four)
        This is an alternative constructor that provides:
        - Automatic generation of event_id if not provided
        - Automatic timestamp if not provided
        - Default version (0) if not provided
        - Clean API for creating events
        
        Why @classmethod?
        - Receives the class (cls) as first argument
        - Can create instances of the class
        - Subclasses inherit and can override
        - Better than __init__ defaults for frozen dataclasses
        
        Args:
            aggregate_id: Required - ID of the aggregate this event relates to
            aggregate_type: Type of aggregate (Strategy, Order, etc.)
            **kwargs: Additional fields (can override defaults)
        
        Returns:
            New event instance
        
        Example:
            # Without factory method (verbose):
            event = SignalGeneratedEvent(
                event_id=str(uuid.uuid4()),
                occurred_at=datetime.utcnow(),
                aggregate_id="strategy-ma-AAPL",
                aggregate_type="Strategy",
                version=0,
                strategy_name="MA",
                symbol="AAPL",
                ...
            )
            
            # With factory method (clean):
            event = SignalGeneratedEvent.create(
                aggregate_id="strategy-ma-AAPL",
                aggregate_type="Strategy",
                strategy_name="MA",
                symbol="AAPL",
                ...
            )
        """
        # Provide defaults for common fields
        if 'event_id' not in kwargs:
            kwargs['event_id'] = str(uuid.uuid4())
        if 'occurred_at' not in kwargs:
            kwargs['occurred_at'] = datetime.utcnow()
        if 'version' not in kwargs:
            kwargs['version'] = 0  # Event store will set actual version
        
        return cls(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            **kwargs
        )
    
    def to_dict(self) -> dict:
        """
        Convert event to dictionary for serialization.
        
        This method is crucial for:
        1. Sending events over network (JSON)
        2. Storing events in PostgreSQL (JSONB)
        3. Logging events
        
        PYTHON FEATURE: asdict()
        The dataclasses.asdict() function automatically converts
        a dataclass to a dictionary. Much cleaner than manual field extraction!
        """
        data = asdict(self)
        
        # Convert special types to JSON-serializable format
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                data[key] = str(value)
        
        # Add event type for deserialization
        data['event_type'] = self.__class__.__name__
        
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BaseEvent':
        """
        Reconstruct event from dictionary.
        
        PYTHON FEATURE: @classmethod
        Method that receives the class as first argument (cls),
        not an instance. Used for alternative constructors.
        
        This is the inverse of to_dict():
        - to_dict(): Event → Dictionary (for storage)
        - from_dict(): Dictionary → Event (for retrieval)
        
        Args:
            data: Dictionary from database or network
        
        Returns:
            Reconstructed event instance
        """
        # Create a copy to avoid modifying original
        event_data = data.copy()
        
        # Remove fields that aren't constructor parameters
        event_data.pop('event_type', None)
        
        # Convert ISO strings back to datetime
        if 'occurred_at' in event_data and isinstance(event_data['occurred_at'], str):
            event_data['occurred_at'] = datetime.fromisoformat(event_data['occurred_at'])
        
        # Provide defaults for event sourcing fields if missing
        # (backward compatibility with events created before Day 7)
        if 'version' not in event_data:
            event_data['version'] = 0
        if 'aggregate_type' not in event_data:
            event_data['aggregate_type'] = ""
        
        return cls(**event_data)




# ============================================================================
# NOTE: Event Definitions Are in Separate Files
# ============================================================================
#
# The events are organized by domain, NOT all in this file:
#
# - SignalGeneratedEvent → src/trading_system/shared_kernel/signal_events.py
# - BacktestCompletedEvent → src/trading_system/shared_kernel/backtest_events.py
# - OrderCreatedEvent, etc. → src/trading_system/order_management/events.py
#
# This file (events.py) contains ONLY BaseEvent!
#
# This separation follows Domain-Driven Design principles:
# - Each bounded context manages its own events
# - Shared kernel provides only the base infrastructure
# - Events live close to the domain they represent
# ============================================================================