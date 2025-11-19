# tests/unit/shared_kernel/test_signal_generated_event.py
# pylint: disable=no-member
"""
Tests for SignalGeneratedEvent.

Note: Pylint disabled for dataclass member access. The @dataclass decorator
creates instance attributes at runtime, but Pylint's static analysis doesn't
recognize them. All assertions below work correctly when tests run.
"""

from decimal import Decimal
from datetime import datetime
import uuid

from trading_system.shared_kernel.signal_events import SignalGeneratedEvent
from trading_system.strategies.signals import SignalType


def test_signal_generated_event_creation_with_factory():
    """Test creating a SignalGeneratedEvent using factory method (RECOMMENDED)."""
    event = SignalGeneratedEvent.create(
        strategy_name="MovingAverageCrossover",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        signal_strength=0.85,
        price=Decimal("150.25"),
        indicators={"fast_ma": 150.45, "slow_ma": 149.80},
        reason="Fast MA crossed above Slow MA"
    )
    
    # Verify fields
    assert event.strategy_name == "MovingAverageCrossover"
    assert event.symbol == "AAPL"
    assert event.signal_type == SignalType.BUY
    assert event.signal_strength == 0.85
    assert event.indicators["fast_ma"] == 150.45
    
    # Verify auto-generated fields
    assert event.event_id is not None  # Auto-generated
    assert event.occurred_at is not None  # Auto-generated
    assert event.aggregate_id == "strategy-MovingAverageCrossover-AAPL"  # Auto-generated
    assert event.aggregate_type == "Strategy"
    assert event.version == 0  # Default version


def test_signal_generated_event_creation_direct():
    """Test creating a SignalGeneratedEvent using direct construction."""
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
    
    assert event.strategy_name == "MovingAverageCrossover"
    assert event.symbol == "AAPL"
    assert event.signal_type == SignalType.BUY
    assert event.signal_strength == 0.85
    assert event.indicators["fast_ma"] == 150.45


def test_signal_generated_event_serialization():
    """Test event serialization and deserialization."""
    # Create using factory method
    original = SignalGeneratedEvent.create(
        strategy_name="RSI",
        symbol="TSLA",
        signal_type=SignalType.SELL,
        signal_strength=0.72,
        price=Decimal("245.50"),
        indicators={"rsi": 75.5},
        reason="RSI overbought"
    )
    
    # Serialize to dict
    data = original.to_dict()
    
    # Check enum was converted to string
    assert data["signal_type"] == "SELL"
    assert data["price"] == "245.50"
    assert data["event_type"] == "SignalGeneratedEvent"
    assert "event_id" in data
    assert "occurred_at" in data
    
    # Deserialize back
    reconstructed = SignalGeneratedEvent.from_dict(data)
    
    # Verify fields match
    assert reconstructed.event_id == original.event_id
    assert reconstructed.strategy_name == original.strategy_name
    assert reconstructed.signal_type == SignalType.SELL  # Back to enum
    assert reconstructed.signal_strength == original.signal_strength
    assert reconstructed.price == original.price
    assert reconstructed.aggregate_id == original.aggregate_id
    assert reconstructed.aggregate_type == original.aggregate_type


def test_signal_validation():
    """Test that validation works correctly."""
    import pytest
    
    # Missing strategy_name
    with pytest.raises(ValueError, match="strategy_name is required"):
        SignalGeneratedEvent.create(
            strategy_name="",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            signal_strength=0.8,
            price=Decimal("150")
        )
    
    # Invalid signal_strength
    with pytest.raises(ValueError, match="signal_strength must be 0.0-1.0"):
        SignalGeneratedEvent.create(
            strategy_name="MA",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            signal_strength=1.5,  # Invalid!
            price=Decimal("150")
        )


def test_factory_method_with_custom_aggregate_id():
    """Test factory method with custom aggregate_id override."""
    event = SignalGeneratedEvent.create(
        aggregate_id="custom-aggregate-id",  # Override default
        strategy_name="TestStrategy",
        symbol="TEST",
        signal_type=SignalType.HOLD,
        signal_strength=0.5,
        price=Decimal("100")
    )
    
    assert event.aggregate_id == "custom-aggregate-id"  # Custom value used
    assert event.aggregate_type == "Strategy"