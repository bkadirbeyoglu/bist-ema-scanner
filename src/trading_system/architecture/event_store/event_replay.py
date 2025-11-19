"""
Event Replay Utilities.

Provides tools to:
- Replay events from PostgreSQL
- Rebuild aggregate state
- Time travel to any point in history
"""

import logging
from typing import List, Optional, Callable, Any
from datetime import datetime

from trading_system.shared_kernel.base_event import BaseEvent
from trading_system.architecture.event_store.postgres_event_store import PostgresEventStore

logger = logging.getLogger(__name__)


class EventReplayer:
    """
    Replays events from event store.
    
    PATTERN: Event Sourcing + Projection
    Rebuilds current state by applying historical events.
    """
    
    def __init__(self, event_store: PostgresEventStore):
        self.event_store = event_store
    
    async def replay_aggregate(
        self,
        aggregate_id: str,
        apply_event: Callable[[Any, BaseEvent], Any],
        initial_state: Any = None,
        until_version: Optional[int] = None
    ) -> Any:
        """
        Replay all events for an aggregate.
        
        Args:
            aggregate_id: Which aggregate to replay
            apply_event: Function that applies event to state
            initial_state: Starting state (default: None)
            until_version: Stop at this version (for time travel)
        
        Returns:
            Current state after replaying all events
        
        Example:
            def apply_signal(state, event):
                if event.signal_type == "BUY":
                    state['position'] = 'LONG'
                elif event.signal_type == "SELL":
                    state['position'] = 'FLAT'
                return state
            
            state = await replayer.replay_aggregate(
                "strategy-ma-AAPL",
                apply_signal,
                initial_state={'position': 'FLAT'}
            )
        """
        # Get event stream
        events = await self.event_store.get_stream(aggregate_id)
        
        # Apply each event
        state = initial_state
        for event in events:
            if until_version and event.version > until_version:
                break
            state = apply_event(state, event)
        
        logger.info(
            f"Replayed {len(events)} events for aggregate {aggregate_id}"
        )
        
        return state
    
    async def replay_signals_for_strategy(
        self,
        strategy_name: str,
        symbol: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[BaseEvent]:
        """
        Replay all signals from a strategy.
        
        Example:
            # Get all MA signals for AAPL in March
            signals = await replayer.replay_signals_for_strategy(
                "MovingAverage",
                "AAPL",
                start_time=datetime(2024, 3, 1),
                end_time=datetime(2024, 4, 1)
            )
        """
        aggregate_id = f"strategy-{strategy_name}-{symbol}"
        
        if start_time and end_time:
            events = await self.event_store.get_events_in_range(
                start_time,
                end_time,
                event_type="SignalGeneratedEvent"
            )
            # Filter by aggregate_id
            return [e for e in events if e.aggregate_id == aggregate_id]
        else:
            return await self.event_store.get_stream(aggregate_id)
    
    async def analyze_strategy_performance(
        self,
        strategy_name: str,
        symbol: str
    ) -> dict:
        """
        Analyze strategy performance from events.
        
        Returns statistics about signals generated.
        """
        signals = await self.replay_signals_for_strategy(strategy_name, symbol)
        
        buy_count = sum(1 for s in signals if s.signal_type == "BUY")
        sell_count = sum(1 for s in signals if s.signal_type == "SELL")
        hold_count = sum(1 for s in signals if s.signal_type == "HOLD")
        
        avg_strength = sum(s.signal_strength for s in signals) / len(signals) if signals else 0
        
        return {
            "strategy": strategy_name,
            "symbol": symbol,
            "total_signals": len(signals),
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "hold_signals": hold_count,
            "average_strength": avg_strength,
            "first_signal": signals[0].occurred_at if signals else None,
            "last_signal": signals[-1].occurred_at if signals else None
        }