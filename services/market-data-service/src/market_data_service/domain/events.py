"""
Market Data Domain Events.

Events published by the Market Data Service for other services to consume.
These are the "contract" between Market Data and the rest of the system.

DESIGN PATTERN: Domain Events
- Represent something that happened in the domain
- Immutable (what happened can't change)
- Published to message queue (SQS now, Kafka later)
- Consumed by other bounded contexts
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid
import json


@dataclass(frozen=True)
class DomainEvent:
    """
    Base class for all domain events.
    
    DESIGN PATTERN: Event Envelope
    - Standard metadata for all events
    - correlation_id: Track related events across services
    - occurred_at: When the event happened (not when processed)
    - event_id: Unique identifier for deduplication
    
    PYTHON FEATURE: frozen=True
    - Events are immutable (can't change what happened)
    - Safe to pass around, cache, etc.
    """
    
    # PYTHON FEATURE: field(default_factory=...)
    # - Generates new UUID for each instance
    # - Can't use mutable default (uuid.uuid4()) directly
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    
    # Correlation ID for distributed tracing
    # Set this to track related events across services
    correlation_id: str | None = None
    
    @property
    def event_type(self) -> str:
        """
        Event type name (class name).
        
        Used for:
        - Event routing in consumers
        - Logging and debugging
        - Schema registry (future)
        
        Example:
            >>> event = PriceUpdatedEvent(...)
            >>> event.event_type
            'PriceUpdatedEvent'
        """
        return self.__class__.__name__
    
    def to_dict(self) -> dict[str, Any]:
        """
        Convert event to dictionary for serialization.
        
        PYTHON FEATURE: dataclasses.asdict()
        - Recursively converts dataclass to dict
        - Handles nested dataclasses
        
        Note: We add event_type explicitly (not a field)
        """
        data = asdict(self)
        data["event_type"] = self.event_type
        
        # Convert datetime to ISO format string
        if isinstance(data.get("occurred_at"), datetime):
            data["occurred_at"] = data["occurred_at"].isoformat()
        
        # Convert Decimal to string to preserve precision
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
        
        return data
    
    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict(), default=str)


@dataclass(frozen=True)
class PriceUpdatedEvent(DomainEvent):
    """
    Published when a security's price changes.
    
    This is the PRIMARY event from Market Data Service.
    
    CONSUMERS:
    - Order Management: Validate order prices
    - Portfolio: Update position valuations
    - Risk: Monitor exposure changes
    - Strategy: Trigger trading signals
    
    MESSAGE QUEUE: market-data-prices
    """
    
    symbol: str = ""
    price: Decimal = Decimal("0")
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: int = 0
    source: str = "unknown"
    
    def __post_init__(self):
        """Validate event data."""
        if not self.symbol:
            raise ValueError("Symbol is required for PriceUpdatedEvent")
        if self.price <= 0:
            raise ValueError(f"Price must be positive, got {self.price}")


@dataclass(frozen=True)
class QuoteReceivedEvent(DomainEvent):
    """
    Published when a full quote (bid/ask) is received.
    
    More detailed than PriceUpdatedEvent, includes market depth.
    
    CONSUMERS:
    - Market Making strategies
    - Spread analysis
    - Liquidity monitoring
    """
    
    symbol: str = ""
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    bid_size: int = 0
    ask_size: int = 0
    last_price: Decimal = Decimal("0")
    volume: int = 0
    source: str = "unknown"


@dataclass(frozen=True)
class DataSourceConnectedEvent(DomainEvent):
    """
    Published when a data source connection is established.
    
    OPERATIONAL EVENT:
    - Used for monitoring and alerting
    - Track data source health
    """
    
    source_name: str = ""
    connected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class DataSourceDisconnectedEvent(DomainEvent):
    """
    Published when a data source connection is lost.
    
    OPERATIONAL EVENT:
    - Triggers alerts
    - May pause dependent services
    """
    
    source_name: str = ""
    reason: str = ""
    will_retry: bool = True
    disconnected_at: datetime = field(default_factory=datetime.utcnow)