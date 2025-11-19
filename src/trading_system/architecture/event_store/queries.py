"""
Common event store queries for debugging and analysis.
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta

from trading_system.shared_kernel.base_event import BaseEvent
from trading_system.shared_kernel.signal_events import SignalGeneratedEvent
from trading_system.shared_kernel.backtest_events import BacktestCompletedEvent
from trading_system.architecture.event_store.postgres_event_store import PostgresEventStore


class EventStoreQueries:
    """
    Pre-built queries for common event store operations.
    
    PATTERN: Query Object
    Encapsulates complex queries in simple methods.
    """
    
    def __init__(self, event_store: PostgresEventStore):
        self.event_store = event_store
    
    async def get_todays_signals(self) -> List[SignalGeneratedEvent]:
        """Get all signals generated today."""
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        
        return await self.event_store.get_events_in_range(
            start, end, "SignalGeneratedEvent"
        )
    
    async def get_signals_by_type(
        self,
        signal_type: str,
        limit: int = 100
    ) -> List[SignalGeneratedEvent]:
        """Get all signals of a specific type (BUY/SELL/HOLD)."""
        query = """
            SELECT *
            FROM signal_events
            WHERE signal_type = $1
            ORDER BY occurred_at DESC
            LIMIT $2
        """
        rows = await self.event_store.pool.fetch(query, signal_type, limit)
        
        # Convert to events (simplified, would need proper deserialization)
        return [self.event_store._deserialize_event(row) for row in rows]
    
    async def find_high_confidence_signals(
        self,
        min_strength: float = 0.8,
        limit: int = 50
    ) -> List[SignalGeneratedEvent]:
        """Find signals with high confidence."""
        query = """
            SELECT *
            FROM signal_events
            WHERE signal_strength >= $1
            ORDER BY occurred_at DESC
            LIMIT $2
        """
        rows = await self.event_store.pool.fetch(query, min_strength, limit)
        return [self.event_store._deserialize_event(row) for row in rows]
    
    async def get_recent_backtests(
        self,
        limit: int = 10
    ) -> List[BacktestCompletedEvent]:
        """Get most recent backtest results."""
        return await self.event_store.get_events_by_type(
            "BacktestCompletedEvent",
            limit
        )
    
    async def compare_strategy_performance(
        self,
        strategy1: str,
        strategy2: str,
        symbol: str,
        days_back: int = 30
    ) -> Dict[str, Any]:
        """Compare two strategies on same symbol."""
        cutoff = datetime.now() - timedelta(days=days_back)
        
        # Get signals for both strategies
        signals1 = await self.event_store.get_events_in_range(
            cutoff, datetime.now(), "SignalGeneratedEvent"
        )
        signals1 = [s for s in signals1 
                   if s.strategy_name == strategy1 and s.symbol == symbol]
        
        signals2 = await self.event_store.get_events_in_range(
            cutoff, datetime.now(), "SignalGeneratedEvent"
        )
        signals2 = [s for s in signals2 
                   if s.strategy_name == strategy2 and s.symbol == symbol]
        
        return {
            "strategy1": {
                "name": strategy1,
                "total_signals": len(signals1),
                "buy_signals": sum(1 for s in signals1 if s.signal_type == "BUY"),
                "avg_strength": sum(s.signal_strength for s in signals1) / len(signals1) if signals1 else 0
            },
            "strategy2": {
                "name": strategy2,
                "total_signals": len(signals2),
                "buy_signals": sum(1 for s in signals2 if s.signal_type == "BUY"),
                "avg_strength": sum(s.signal_strength for s in signals2) / len(signals2) if signals2 else 0
            }
        }