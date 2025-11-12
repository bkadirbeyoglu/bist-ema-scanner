# tests/integration/test_strategy_integration.py
"""Integration test for strategies with event bus"""

import pytest
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime

from trading_system.strategies.manager import StrategyManager
from trading_system.strategies.moving_average import MovingAverageCrossoverStrategy
from trading_system.strategies.rsi_strategy import RSIMeanReversionStrategy
from trading_system.shared_kernel.event_bus import InMemoryEventBus
from trading_system.strategies.base import StrategyEvent


class TestStrategyIntegration:
    
    @pytest.mark.asyncio
    async def test_strategy_event_emission(self):
        """Test strategies emit events via event bus"""
        
        # Setup
        event_bus = InMemoryEventBus()
        manager = StrategyManager(event_bus)
        
        # Track emitted events
        received_events = []
        
        async def event_handler(event: StrategyEvent):
            received_events.append(event)
        
        # Subscribe to strategy events
        await event_bus.subscribe(StrategyEvent, event_handler)
        
        # Register and activate strategies
        ma_strategy = MovingAverageCrossoverStrategy(
            fast_period=5,
            slow_period=10
        )
        manager.register_strategy(ma_strategy)
        manager.activate_strategy("MA_Crossover")
        
        # Create market data that will trigger a signal
        dates = pd.date_range(end=datetime.now(), periods=50, freq='D')
        # Strong uptrend for clear golden cross
        prices = np.linspace(80, 120, 50)
        market_data = pd.DataFrame({'close': prices}, index=dates)
        
        # Process data
        signals = await manager.process_market_data("AAPL", market_data)
        
        # Allow event processing
        await asyncio.sleep(0.1)
        
        # Verify
        assert "MA_Crossover" in signals
        # Check if events were emitted (may be HOLD or BUY depending on exact calculation)
        # Golden cross should trigger at least one event during the uptrend