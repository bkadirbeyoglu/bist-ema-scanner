# src/trading_system/shared_kernel/signal_events.py
"""
Signal Events for Trading Strategies.

Events published when trading strategies generate buy/sell signals.
These events are optimized for event sourcing with a flat structure.

CORRECTED VERSION:
- Fixed dataclass field ordering for proper inheritance
- Uses field(default_factory=dict) for mutable defaults
- Uses SignalType enum for type safety
"""

from dataclasses import dataclass, field
from typing import ClassVar
from decimal import Decimal
from datetime import datetime

from trading_system.shared_kernel.base_event import BaseEvent
from trading_system.strategies.signals import SignalType


@dataclass(frozen=True)
class SignalGeneratedEvent(BaseEvent):
    """
    Event published when a trading strategy generates a signal.
    
    CRITICAL: Field ordering for dataclass inheritance.
    When inheriting from a dataclass with default values, ALL child fields
    must also have default values.
    """
    
    # ALL FIELDS MUST HAVE DEFAULTS (because BaseEvent has defaults)
    # Required fields - use empty string or None as sentinel values
    strategy_name: str = ""      # Which strategy generated this?
    symbol: str = ""             # Which stock/asset?
    signal_type: SignalType = SignalType.HOLD  # Type-safe: BUY, SELL, or HOLD
    signal_strength: float = 0.0  # 0.0 to 1.0 (granular confidence level)
    price: Decimal = Decimal("0")  # Current price
    
    # Optional fields with sensible defaults
    indicators: dict = field(default_factory=dict)  # All indicator values
    reason: str = ""  # Why this signal?
    
    # Event sourcing metadata
    aggregate_type: str = "Strategy"  # Categorizes this as a Strategy event
    version: int = 0  # Event version (Event Store will set actual value)
    
    # Class variable for event routing
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
        
        This is the RECOMMENDED way to create events - it handles all the
        auto-generation of IDs, timestamps, etc.
        """
        # Automatic aggregate_id generation
        aggregate_id = kwargs.pop('aggregate_id', f"strategy-{strategy_name}-{symbol}")
        
        # Call parent factory method
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type="Strategy",
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
        Validate signal data after initialization.
        """
        if not self.strategy_name:
            raise ValueError("strategy_name is required")
        if not self.symbol:
            raise ValueError("symbol is required")
        if not isinstance(self.signal_type, SignalType):
            raise TypeError(f"signal_type must be SignalType enum, got {type(self.signal_type)}")
        if not 0.0 <= self.signal_strength <= 1.0:
            raise ValueError(f"signal_strength must be 0.0-1.0, got {self.signal_strength}")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            **super().to_dict(),
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,  # ← CRITICAL: Convert enum to string
            "signal_strength": self.signal_strength,
            "price": str(self.price),  # ← Decimal to string
            "indicators": self.indicators,
            "reason": self.reason,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SignalGeneratedEvent":
        """Reconstruct event from dictionary."""
        return cls(
            event_id=data["event_id"],
            aggregate_id=data["aggregate_id"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            strategy_name=data.get("strategy_name", ""),
            symbol=data.get("symbol", ""),
            signal_type=SignalType(data.get("signal_type", "HOLD")),
            signal_strength=data.get("signal_strength", 0.0),
            price=Decimal(data.get("price", "0")),
            indicators=data.get("indicators", {}),
            reason=data.get("reason", ""),
            aggregate_type=data.get("aggregate_type", "Strategy"),
            version=data.get("version", 0)
        )