# pylint: disable=no-member,unexpected-keyword-arg,no-value-for-parameter
"""
Integration tests for PostgreSQL Event Store.

These tests require a running PostgreSQL instance.
Run: docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres

Pylint Suppressions:
- no-member: Dataclass members created at runtime
- unexpected-keyword-arg: Dataclass inheritance with frozen=True confuses Pylint
- no-value-for-parameter: Dataclass default values not recognized in static analysis
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import uuid4

from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.architecture.event_store.postgres_event_store import (
    PostgresEventStore,
    ConcurrencyError
)
from trading_system.shared_kernel.signal_events import SignalGeneratedEvent
from trading_system.strategies.signals import SignalType


@pytest.fixture(scope="function")
async def connection_pool():
    """Create test database connection."""
    pool = PostgresConnectionPool(
        host="localhost",
        port=5432,
        database="trading_db",
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
    """Clean events table before each test."""
    await connection_pool.execute("DELETE FROM events.events")
    yield


@pytest.mark.asyncio
async def test_store_signal_generated_event(event_store, clean_database):
    """Test storing SignalGeneratedEvent."""
    # Use factory method to create event
    event = SignalGeneratedEvent.create(
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
    
    # Verify it was stored
    assert seq is not None
    assert seq > 0
    
    # Retrieve and verify
    events = await event_store.get_events(event.aggregate_id)
    assert len(events) == 1
    
    stored_event = events[0]
    assert stored_event["strategy_name"] == "TestStrategy"
    assert stored_event["symbol"] == "AAPL"
    assert stored_event["signal_type"] == "BUY"
    assert stored_event["signal_strength"] == 0.85


@pytest.mark.asyncio
async def test_query_signals_by_type(event_store, clean_database):
    """Test querying signals by type."""
    # Create multiple signals
    for i in range(5):
        signal_type = SignalType.BUY if i % 2 == 0 else SignalType.SELL
        event = SignalGeneratedEvent.create(
            strategy_name="TestStrategy",
            symbol="AAPL",
            signal_type=signal_type,
            signal_strength=0.75,
            price=Decimal("150.00")
        )
        await event_store.append(event)
    
    # Query by type
    events = await event_store.get_events_by_type("SignalGeneratedEvent", limit=10)
    
    # Verify
    assert len(events) == 5
    assert all(e["event_type"] == "SignalGeneratedEvent" for e in events)
    
    # Count BUY vs SELL
    buy_count = sum(1 for e in events if e["signal_type"] == "BUY")
    sell_count = sum(1 for e in events if e["signal_type"] == "SELL")
    assert buy_count == 3  # indices 0, 2, 4
    assert sell_count == 2  # indices 1, 3


@pytest.mark.asyncio
async def test_event_ordering(event_store, clean_database):
    """Test that events are ordered correctly."""
    # Use unique aggregate_id to avoid conflicts between test runs
    aggregate_id = f"strategy-test-TSLA-{uuid4()}"
    
    # CRITICAL FIX: Use factory method OR don't pass version field
    # The event store will automatically assign the correct version
    for i in range(3):
        event = SignalGeneratedEvent.create(
            aggregate_id=aggregate_id,  # Pass specific aggregate_id
            strategy_name="TestStrategy",
            symbol="TSLA",
            signal_type=SignalType.HOLD,
            signal_strength=0.5 + (i * 0.1),
            price=Decimal("200.00")
        )
        await event_store.append(event)
    
    # Retrieve events
    events = await event_store.get_events(aggregate_id)
    
    # Debug: print actual versions
    print(f"\nAggregate ID: {aggregate_id}")
    print(f"Retrieved {len(events)} events")
    for idx, evt in enumerate(events):
        print(f"  Event {idx}: version={evt['version']}, seq={evt['sequence_number']}")
    
    # Verify order and count
    assert len(events) == 3, f"Expected 3 events, got {len(events)}"
    
    # Verify versions are sequential starting from 0
    for i, event in enumerate(events):
        assert event["version"] == i, f"Event {i}: expected version {i}, got {event['version']}"


@pytest.mark.asyncio
async def test_get_statistics(event_store, clean_database):
    """Test event store statistics."""
    # Add some events
    for i in range(10):
        event = SignalGeneratedEvent.create(
            strategy_name="TestStrategy",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            signal_strength=0.8,
            price=Decimal("150.00")
        )
        await event_store.append(event)
    
    # Get statistics
    stats = await event_store.get_statistics()
    
    # Verify
    assert stats["total_events"] == 10
    assert "SignalGeneratedEvent" in stats["event_types"]
    assert stats["event_types"]["SignalGeneratedEvent"] == 10
    assert "Strategy" in stats["aggregate_types"]
    assert stats["aggregate_types"]["Strategy"] == 10


@pytest.mark.asyncio
async def test_concurrency_control(event_store, clean_database):
    """
    Test optimistic concurrency control.
    
    HOW VERSION CONTROL ACTUALLY WORKS:
    Initial: No events exist (current_version = -1)
    1. First append: next_version = 0, stored with version=0, current becomes 0
    2. Second append with expected_version=0: SUCCEEDS (current is 0, we expect 0)
    3. Third append with expected_version=0: FAILS (current is 1, we expect 0 - stale!)
    """
    aggregate_id = f"strategy-concurrency-test-{uuid4()}"
    
    # Create first event - don't specify version, let event store assign it
    event1 = SignalGeneratedEvent.create(
        aggregate_id=aggregate_id,
        strategy_name="TestStrategy",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        signal_strength=0.7,
        price=Decimal("150.00")
    )
    seq1 = await event_store.append(event1)
    assert seq1 is not None
    print(f"\nFirst event appended with seq={seq1}")
    # After first append: current_version in DB is 0 (the version we just stored)
    
    # Create second event
    event2 = SignalGeneratedEvent.create(
        aggregate_id=aggregate_id,
        strategy_name="TestStrategy",
        symbol="AAPL",
        signal_type=SignalType.SELL,
        signal_strength=0.6,
        price=Decimal("151.00")
    )
    
    # This should SUCCEED - current version is 0, and we expect 0 (fresh read)
    print("Testing fresh read (expecting success)...")
    seq2 = await event_store.append(event2, expected_version=0)
    assert seq2 is not None
    print(f"Second event appended with seq={seq2}")
    # After second append: current_version in DB is 1
    
    # Create third event
    event3 = SignalGeneratedEvent.create(
        aggregate_id=aggregate_id,
        strategy_name="TestStrategy",
        symbol="AAPL",
        signal_type=SignalType.HOLD,
        signal_strength=0.5,
        price=Decimal("152.00")
    )
    
    # This should FAIL - current version is 1, but we expect 0 (stale read!)
    print("Testing stale read (expecting failure)...")
    with pytest.raises(ConcurrencyError) as exc_info:
        await event_store.append(event3, expected_version=0)
    print(f"Correctly raised ConcurrencyError: {exc_info.value}")
    
    # This should SUCCEED - current version is 1, and we expect 1 (fresh read)
    print("Testing fresh read again (expecting success)...")
    seq3 = await event_store.append(event3, expected_version=1)
    assert seq3 is not None
    print(f"Third event appended with seq={seq3}")
    # After third append: current_version in DB is 2
    
    # Create fourth event to test another conflict
    event4 = SignalGeneratedEvent.create(
        aggregate_id=aggregate_id,
        strategy_name="TestStrategy",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        signal_strength=0.8,
        price=Decimal("153.00")
    )
    
    # This should FAIL - current version is 2, but we expect 1 (stale!)
    print("Testing another stale read (expecting failure)...")
    with pytest.raises(ConcurrencyError) as exc_info:
        await event_store.append(event4, expected_version=1)
    print(f"Correctly raised ConcurrencyError: {exc_info.value}")
    
    # Verify all 3 events were stored with correct versions (0, 1, 2)
    events = await event_store.get_events(aggregate_id)
    assert len(events) == 3
    assert events[0]["version"] == 0
    assert events[1]["version"] == 1
    assert events[2]["version"] == 2


@pytest.mark.asyncio
async def test_time_range_query(event_store, clean_database):
    """Test querying events by time range."""
    now = datetime.utcnow()
    
    # Create event in the past
    event1 = SignalGeneratedEvent.create(
        aggregate_id="strategy-test-1",
        strategy_name="TestStrategy",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        signal_strength=0.7,
        price=Decimal("150.00")
    )
    # Manually override occurred_at for testing
    event1 = SignalGeneratedEvent(
        event_id=event1.event_id,
        aggregate_id=event1.aggregate_id,
        occurred_at=now - timedelta(hours=2),  # Override timestamp
        aggregate_type=event1.aggregate_type,
        version=event1.version,
        strategy_name=event1.strategy_name,
        symbol=event1.symbol,
        signal_type=event1.signal_type,
        signal_strength=event1.signal_strength,
        price=event1.price
    )
    await event_store.append(event1)
    
    # Create event now
    event2 = SignalGeneratedEvent.create(
        aggregate_id="strategy-test-2",
        strategy_name="TestStrategy",
        symbol="AAPL",
        signal_type=SignalType.SELL,
        signal_strength=0.8,
        price=Decimal("151.00")
    )
    await event_store.append(event2)
    
    # Query last hour (should get only event2)
    events = await event_store.get_events_by_time_range(
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
        aggregate_type="Strategy"
    )
    
    assert len(events) >= 1  # At least event2
    
    # Query last 3 hours (should get both)
    events = await event_store.get_events_by_time_range(
        start_time=now - timedelta(hours=3),
        end_time=now + timedelta(hours=1),
        aggregate_type="Strategy"
    )
    
    assert len(events) >= 2  # At least both events