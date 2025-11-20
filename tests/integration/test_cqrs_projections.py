"""
Integration tests for CQRS projections.

TESTS:
- SignalGeneratedEvent → Read model projection
- Query read model
- Compare with event store replay
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime

from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.architecture.event_store.postgres_event_store import PostgresEventStore
from trading_system.shared_kernel.signal_events import SignalGeneratedEvent, SignalType
from trading_system.projections.setup import setup_projection_system
from trading_system.queries.strategy_queries import StrategyQueryService


@pytest.fixture
async def projection_system():
    """Setup complete CQRS system for testing."""
    pool = PostgresConnectionPool(
        host="localhost",
        port=5432,
        database="trading_db",
        user="trading",
        password="password"  # Default password from PostgresConnectionPool
    )
    await pool.connect()
    
    # Clean up any existing test data before running tests
    async with pool.pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE read_models.strategy_performance CASCADE")
        await conn.execute("TRUNCATE TABLE read_models.signal_analytics CASCADE")
        await conn.execute("TRUNCATE TABLE read_models.backtest_summaries CASCADE")
        await conn.execute("TRUNCATE TABLE events.events CASCADE")
        await conn.execute("TRUNCATE TABLE read_models.projection_checkpoints CASCADE")
    
    event_store = PostgresEventStore(pool)
    engine = await setup_projection_system(pool, event_store)
    query_service = StrategyQueryService(pool)
    
    yield {
        "event_store": event_store,
        "engine": engine,
        "query_service": query_service,
        "pool": pool
    }
    
    # Clean up after tests
    async with pool.pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE read_models.strategy_performance CASCADE")
        await conn.execute("TRUNCATE TABLE read_models.signal_analytics CASCADE")
        await conn.execute("TRUNCATE TABLE read_models.backtest_summaries CASCADE")
        await conn.execute("TRUNCATE TABLE events.events CASCADE")
        await conn.execute("TRUNCATE TABLE read_models.projection_checkpoints CASCADE")
    
    await pool.disconnect()


@pytest.mark.asyncio
async def test_signal_projection(projection_system):
    """
    Test complete flow: Event → Projection → Query
    """
    event_store = projection_system["event_store"]
    engine = projection_system["engine"]
    query_service = projection_system["query_service"]
    
    # 1. Generate signal event
    signal = SignalGeneratedEvent.create(
        aggregate_id="strategy-test-AAPL",
        strategy_name="TestStrategy",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        signal_strength=0.85,
        price=Decimal("150.00"),
        reason="Test signal",
        indicators={"sma_20": 148.5}
    )
    
    # 2. Save to event store
    await event_store.append(signal)
    
    # 3. Project to read model
    await engine.catch_up("SignalProjection")
    
    # 4. Query read model
    performance = await query_service.get_strategy_performance("strategy-test-AAPL")
    
    # 5. Verify projection
    assert performance is not None
    assert performance.strategy_name == "TestStrategy"
    assert performance.symbol == "AAPL"
    assert performance.total_signals == 1
    assert performance.buy_signals == 1
    assert performance.sell_signals == 0


@pytest.mark.asyncio
async def test_projection_idempotency(projection_system):
    """
    Test projecting same event twice = same result.
    
    CRITICAL: Projections must be idempotent for replay.
    """
    event_store = projection_system["event_store"]
    engine = projection_system["engine"]
    query_service = projection_system["query_service"]
    
    # Generate signal
    signal = SignalGeneratedEvent.create(
        aggregate_id="strategy-idempotent-test",
        strategy_name="IdempotentTest",
        symbol="GOOGL",
        signal_type=SignalType.SELL,
        signal_strength=0.75,
        price=Decimal("2800.00"),
        reason="Idempotency test",
        indicators={}
    )
    
    await event_store.append(signal)
    
    # Project twice
    await engine.catch_up("SignalProjection")
    await engine.catch_up("SignalProjection")  # Second time
    
    # Should only have ONE signal
    performance = await query_service.get_strategy_performance("strategy-idempotent-test")
    assert performance.total_signals == 1  # Not 2!


@pytest.mark.asyncio
async def test_read_model_performance(projection_system):
    """
    Compare query performance: Event store vs Read model.
    """
    import time
    
    event_store = projection_system["event_store"]
    engine = projection_system["engine"]
    query_service = projection_system["query_service"]
    
    # Generate 100 signals
    strategy_id = "strategy-perf-test"
    for i in range(100):
        signal = SignalGeneratedEvent.create(
            aggregate_id=strategy_id,
            strategy_name="PerfTest",
            symbol="SPY",
            signal_type=SignalType.BUY if i % 2 == 0 else SignalType.SELL,
            signal_strength=0.8,
            price=Decimal("450.00"),
            reason=f"Signal {i}",
            indicators={}
        )
        await event_store.append(signal)
    
    # Project all events
    await engine.catch_up("SignalProjection")
    
    # Method 1: Query read model (FAST)
    start = time.time()
    performance = await query_service.get_strategy_performance(strategy_id)
    read_model_time = time.time() - start
    
    # Method 2: Count from event store (SLOW)
    start = time.time()
    events = await event_store.get_events(
        aggregate_id=strategy_id
    )
    event_store_time = time.time() - start
    
    print(f"Read model query: {read_model_time*1000:.2f}ms")
    print(f"Event store query: {event_store_time*1000:.2f}ms")
    
    # Read model should be much faster
    assert read_model_time < event_store_time
    assert performance.total_signals == 100