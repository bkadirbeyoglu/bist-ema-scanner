# pylint: disable=no-member
"""
Integration tests for PostgreSQL event store.

Note: Pylint disabled for dataclass member access. The @dataclass decorator
creates instance attributes at runtime, but Pylint's static analysis doesn't
recognize them. All assertions below work correctly when tests run.
"""

import pytest
import asyncio
from datetime import datetime
from decimal import Decimal
import uuid

from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.architecture.event_store.postgres_event_store import PostgresEventStore
from trading_system.shared_kernel.signal_events import SignalGeneratedEvent
from trading_system.strategies.signals import SignalType


@pytest.fixture
async def connection_pool():
    """Create test database connection."""
    pool = PostgresConnectionPool(
        host="localhost",
        port=5432,
        database="trading_db",   # ← Single database with schemas
        user="trading",
        password="password"
    )
    await pool.connect()
    yield pool
    await pool.disconnect()


@pytest.fixture
async def event_store(connection_pool):
    """Create event store instance."""
    return PostgresEventStore(connection_pool)


@pytest.fixture
async def clean_database(connection_pool):
    """Clean database before each test."""
    await connection_pool.execute("TRUNCATE TABLE events CASCADE")


@pytest.mark.asyncio
async def test_store_signal_generated_event(event_store, clean_database):
    """Test storing SignalGeneratedEvent."""
    event = SignalGeneratedEvent(
        event_id=str(uuid.uuid4()),
        aggregate_id="strategy-test-AAPL",
        occurred_at=datetime.utcnow(),
        strategy_name="TestStrategy",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        signal_strength=0.85,
        price=Decimal("150.25"),
        indicators={"ma_fast": 151.0, "ma_slow": 149.0},
        reason="Test signal"
    )
    
    # Store event
    seq = await event_store.append(event)
    assert seq > 0
    
    # Retrieve event
    events = await event_store.get_stream("strategy-test-AAPL")
    assert len(events) == 1
    assert events[0].symbol == "AAPL"
    assert events[0].signal_type == SignalType.BUY


@pytest.mark.asyncio
async def test_query_signals_by_type(event_store, clean_database):
    """Test querying signals by type."""
    # Create multiple signals
    for i in range(5):
        signal_type = SignalType.BUY if i % 2 == 0 else SignalType.SELL
        event = SignalGeneratedEvent(
            event_id=str(uuid.uuid4()),
            aggregate_id=f"strategy-test-AAPL-{i}",
            occurred_at=datetime.utcnow(),
            strategy_name="TestStrategy",
            symbol="AAPL",
            signal_type=signal_type,
            signal_strength=0.75,
            price=Decimal("150.00")
        )
        await event_store.append(event)
    
    # Query by type
    all_events = await event_store.get_events_by_type("SignalGeneratedEvent")
    assert len(all_events) == 5


@pytest.mark.asyncio
async def test_event_ordering(event_store, clean_database):
    """Test that events are ordered correctly."""
    aggregate_id = "strategy-test-TSLA"
    
    # Create 3 events
    for i in range(3):
        event = SignalGeneratedEvent(
            event_id=str(uuid.uuid4()),
            aggregate_id=aggregate_id,
            occurred_at=datetime.utcnow(),
            strategy_name="TestStrategy",
            symbol="TSLA",
            signal_type=SignalType.HOLD,
            signal_strength=0.5 + (i * 0.1),
            price=Decimal("200.00")
        )
        await event_store.append(event)
        await asyncio.sleep(0.01)  # Ensure different timestamps
    
    # Retrieve stream
    events = await event_store.get_stream(aggregate_id)
    
    # Verify ordering
    assert len(events) == 3
    assert events[0].version == 1
    assert events[1].version == 2
    assert events[2].version == 3


@pytest.mark.asyncio
async def test_get_statistics(event_store, clean_database):
    """Test event store statistics."""
    # Add some events
    for i in range(10):
        event = SignalGeneratedEvent(
            event_id=str(uuid.uuid4()),
            aggregate_id=f"strategy-test-{i}",
            occurred_at=datetime.utcnow(),
            strategy_name="TestStrategy",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            signal_strength=0.8,
            price=Decimal("150.00")
        )
        await event_store.append(event)
    
    # Get statistics
    stats = await event_store.get_statistics()
    
    assert stats['total_events'] == 10
    assert stats['total_aggregates'] == 10
    assert 'SignalGeneratedEvent' in stats['events_by_type']


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])