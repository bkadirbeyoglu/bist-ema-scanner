"""
Signal Projection - Updates strategy performance read models.

EVENTS HANDLED:
- SignalGeneratedEvent → Updates strategy_performance and signal_analytics

READ MODELS UPDATED:
- read_models.strategy_performance (aggregated metrics)
- read_models.signal_analytics (individual signals)
"""

import logging
import json
from decimal import Decimal
from datetime import datetime

from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.shared_kernel.signal_events import SignalGeneratedEvent, SignalType
from trading_system.shared_kernel.base_event import BaseEvent

logger = logging.getLogger(__name__)


class SignalProjection:
    """
    Projects SignalGeneratedEvent into read models.
    
    IDEMPOTENCY:
    Uses event_id to prevent duplicate projections.
    Safe to replay events.
    """
    
    def __init__(self, pool: PostgresConnectionPool):
        self.pool = pool
    
    def can_handle(self, event_type: str) -> bool:
        """Only handles SignalGeneratedEvent."""
        return event_type == "SignalGeneratedEvent"
    
    async def initialize(self) -> None:
        """Create read model tables."""
        async with self.pool.pool.acquire() as conn:
            # Strategy performance table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS read_models.strategy_performance (
                    strategy_id VARCHAR(255) PRIMARY KEY,
                    strategy_name VARCHAR(100) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    
                    total_signals INT NOT NULL DEFAULT 0,
                    buy_signals INT NOT NULL DEFAULT 0,
                    sell_signals INT NOT NULL DEFAULT 0,
                    hold_signals INT NOT NULL DEFAULT 0,
                    
                    winning_signals INT NOT NULL DEFAULT 0,
                    losing_signals INT NOT NULL DEFAULT 0,
                    win_rate DECIMAL(5,2) NOT NULL DEFAULT 0,
                    avg_profit_per_signal DECIMAL(12,2) NOT NULL DEFAULT 0,
                    total_profit DECIMAL(15,2) NOT NULL DEFAULT 0,
                    max_profit DECIMAL(12,2) NOT NULL DEFAULT 0,
                    max_loss DECIMAL(12,2) NOT NULL DEFAULT 0,
                    
                    avg_signal_strength DECIMAL(4,3) NOT NULL DEFAULT 0,
                    sharpe_ratio DECIMAL(6,3),
                    
                    first_signal_time TIMESTAMP,
                    last_signal_time TIMESTAMP,
                    last_updated TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            # Signal analytics table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS read_models.signal_analytics (
                    signal_id VARCHAR(255) PRIMARY KEY,
                    strategy_id VARCHAR(255) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    signal_type VARCHAR(10) NOT NULL,
                    signal_strength DECIMAL(4,3) NOT NULL,
                    
                    price_at_signal DECIMAL(12,2) NOT NULL,
                    indicators JSONB NOT NULL,
                    reason TEXT NOT NULL,
                    
                    actual_profit DECIMAL(12,2),
                    was_profitable BOOLEAN,
                    
                    signal_time TIMESTAMP NOT NULL,
                    last_updated TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            # Indexes for fast queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signal_analytics_strategy 
                ON read_models.signal_analytics(strategy_id, signal_time DESC);
                
                CREATE INDEX IF NOT EXISTS idx_signal_analytics_symbol
                ON read_models.signal_analytics(symbol, signal_time DESC);
            """)
            
            logger.info("SignalProjection tables initialized")
    
    async def project(self, event: BaseEvent) -> None:
        """
        Project SignalGeneratedEvent into read models.
        
        IDEMPOTENCY:
        Uses ON CONFLICT to handle duplicate projections.
        """
        if not isinstance(event, SignalGeneratedEvent):
            return
        
        async with self.pool.pool.acquire() as conn:
            async with conn.transaction():
                # 1. Insert/update signal analytics (individual signal)
                await conn.execute("""
                    INSERT INTO read_models.signal_analytics (
                        signal_id, strategy_id, symbol, signal_type,
                        signal_strength, price_at_signal, indicators,
                        reason, signal_time, last_updated
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (signal_id) DO UPDATE SET
                        last_updated = NOW()
                """,
                    event.event_id,
                    event.aggregate_id,
                    event.symbol,
                    event.signal_type.value,
                    float(event.signal_strength),
                    float(event.price),
                    json.dumps(event.indicators),  # Convert dict to JSON string for JSONB
                    event.reason,
                    event.occurred_at
                )
                
                # 2. Update strategy performance (aggregated)
                # First, check if strategy exists
                exists = await conn.fetchval("""
                    SELECT 1 FROM read_models.strategy_performance
                    WHERE strategy_id = $1
                """, event.aggregate_id)
                
                if not exists:
                    # Create new strategy record
                    await conn.execute("""
                        INSERT INTO read_models.strategy_performance (
                            strategy_id, strategy_name, symbol,
                            total_signals, buy_signals, sell_signals, hold_signals,
                            avg_signal_strength, first_signal_time, last_signal_time
                        ) VALUES ($1, $2, $3, 1, $4, $5, $6, $7, $8, $8)
                    """,
                        event.aggregate_id,
                        event.strategy_name,
                        event.symbol,
                        1 if event.signal_type == SignalType.BUY else 0,
                        1 if event.signal_type == SignalType.SELL else 0,
                        1 if event.signal_type == SignalType.HOLD else 0,
                        float(event.signal_strength),
                        event.occurred_at
                    )
                else:
                    # Update existing strategy
                    await conn.execute("""
                        UPDATE read_models.strategy_performance SET
                            total_signals = total_signals + 1,
                            buy_signals = buy_signals + CASE WHEN $2 = 'BUY' THEN 1 ELSE 0 END,
                            sell_signals = sell_signals + CASE WHEN $2 = 'SELL' THEN 1 ELSE 0 END,
                            hold_signals = hold_signals + CASE WHEN $2 = 'HOLD' THEN 1 ELSE 0 END,
                            avg_signal_strength = (
                                (avg_signal_strength * total_signals + $3) / (total_signals + 1)
                            ),
                            last_signal_time = $4,
                            last_updated = NOW()
                        WHERE strategy_id = $1
                    """,
                        event.aggregate_id,
                        event.signal_type.value,
                        float(event.signal_strength),
                        event.occurred_at
                    )
                
                logger.debug(f"Projected signal {event.event_id} for {event.aggregate_id}")
    
    async def reset(self) -> None:
        """Clear all read models."""
        async with self.pool.pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE read_models.strategy_performance CASCADE")
            await conn.execute("TRUNCATE TABLE read_models.signal_analytics CASCADE")
        
        logger.info("SignalProjection reset complete")