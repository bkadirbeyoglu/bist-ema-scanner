"""
Setup projection system - wires all components together.
"""

import logging
from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.architecture.event_store.postgres_event_store import PostgresEventStore
from trading_system.projections.engine import ProjectionEngine
from trading_system.projections.signal_projection import SignalProjection
from trading_system.projections.backtest_projection import BacktestProjection

logger = logging.getLogger(__name__)


async def setup_projection_system(
    pool: PostgresConnectionPool,
    event_store: PostgresEventStore
) -> ProjectionEngine:
    """
    Initialize complete projection system.
    
    Returns configured projection engine ready to process events.
    """
    # Create projection engine
    engine = ProjectionEngine(event_store, pool)
    await engine.initialize()
    
    # Create and register projections
    signal_projection = SignalProjection(pool)
    await signal_projection.initialize()
    engine.register_projection(signal_projection)
    
    backtest_projection = BacktestProjection(pool)
    await backtest_projection.initialize()
    engine.register_projection(backtest_projection)
    
    logger.info("Projection system setup complete")
    return engine


async def start_projection_worker(engine: ProjectionEngine):
    """
    Background worker that continuously projects new events.
    
    This would run as a separate service in production.
    """
    import asyncio
    
    logger.info("Starting projection worker...")
    
    while True:
        try:
            # Catch up all projections
            await engine.catch_up("SignalProjection")
            await engine.catch_up("BacktestProjection")
            
            # Wait before next cycle
            await asyncio.sleep(5)  # Process every 5 seconds
            
        except Exception as e:
            logger.error(f"Projection worker error: {e}", exc_info=True)
            await asyncio.sleep(10)  # Back off on error