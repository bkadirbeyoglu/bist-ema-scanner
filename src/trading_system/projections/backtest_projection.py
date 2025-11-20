"""
Backtest Projection - Summarizes backtest results.

EVENTS HANDLED:
- BacktestCompletedEvent → Creates backtest_summaries

READ MODELS UPDATED:
- read_models.backtest_summaries
"""

import logging
import json
from datetime import datetime

from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.shared_kernel.backtest_events import BacktestCompletedEvent
from trading_system.shared_kernel.base_event import BaseEvent

logger = logging.getLogger(__name__)


class BacktestProjection:
    """
    Projects BacktestCompletedEvent into summaries.
    """
    
    def __init__(self, pool: PostgresConnectionPool):
        self.pool = pool
    
    def can_handle(self, event_type: str) -> bool:
        """Only handles BacktestCompletedEvent."""
        return event_type == "BacktestCompletedEvent"
    
    async def initialize(self) -> None:
        """Create backtest summaries table."""
        async with self.pool.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS read_models.backtest_summaries (
                    backtest_id VARCHAR(255) PRIMARY KEY,
                    strategy_name VARCHAR(100) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    
                    parameters JSONB NOT NULL,
                    
                    total_return DECIMAL(8,2) NOT NULL,
                    sharpe_ratio DECIMAL(6,3) NOT NULL,
                    max_drawdown DECIMAL(6,2) NOT NULL,
                    
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP NOT NULL,
                    last_updated TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            # Indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_strategy_symbol
                ON read_models.backtest_summaries(strategy_name, symbol, total_return DESC);
            """)
            
            logger.info("BacktestProjection tables initialized")
    
    async def project(self, event: BaseEvent) -> None:
        """Project BacktestCompletedEvent."""
        if not isinstance(event, BacktestCompletedEvent):
            return
        
        async with self.pool.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO read_models.backtest_summaries (
                    backtest_id, strategy_name, symbol, parameters,
                    total_return, sharpe_ratio, max_drawdown,
                    start_date, end_date, completed_at, last_updated
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ON CONFLICT (backtest_id) DO UPDATE SET
                    last_updated = NOW()
            """,
                event.event_id,
                event.strategy_name,
                event.symbol,
                json.dumps(event.parameters),  # Convert dict to JSON string for JSONB
                float(event.total_return),
                float(event.sharpe_ratio),
                float(event.max_drawdown),
                event.start_date,
                event.end_date,
                event.occurred_at
            )
            
            logger.debug(f"Projected backtest {event.event_id}")
    
    async def reset(self) -> None:
        """Clear backtest summaries."""
        async with self.pool.pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE read_models.backtest_summaries CASCADE")
        
        logger.info("BacktestProjection reset complete")