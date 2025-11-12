import asyncio
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime

from trading_system.strategies.base import TradingStrategy
from trading_system.shared_kernel.event_bus import EventBus


class StrategyManager:
    """
    Manages multiple trading strategies.
    
    Coordinates strategy execution and ensures strategies
    don't conflict with each other.
    """

    def __init__(self, event_bus: EventBus):
        """Initialize with event bus for signal distribution"""
        self.event_bus = event_bus
        self.strategies: Dict[str, TradingStrategy] = {}
        self.active_strategies: List[str] = []

    def register_strategy(self, strategy: TradingStrategy) -> None:
        """Register a new strategy"""
        strategy.event_bus = self.event_bus  # Inject event bus
        self.strategies[strategy.name] = strategy

    def activate_strategy(self, name: str) -> None:
        """Activate a strategy for trading"""
        if name in self.strategies:
            self.active_strategies.append(name)

    def deactivate_strategy(self, name: str) -> None:
        """Deactivate a strategy"""
        if name in self.active_strategies:
            self.active_strategies.remove(name)

    async def process_market_data(self,
                                  symbol: str,
                                  market_data: pd.DataFrame) -> Dict[str, TradingSignal]:
        """
        Process market data through all active strategies.
        
        Returns dict of strategy_name -> signal
        """
        signals = {}

        # Run strategies concurrently
        tasks = []
        for name in self.active_strategies:
            strategy = self.strategies[name]
            task = strategy.analyze_and_emit(market_data, symbol)
            tasks.append((name, task))

        # Gather results
        for name, task in tasks:
            try:
                signal = await task
                signals[name] = signal
            except Exception as e:
                print(f"Strategy {name} failed: {e}")
                # Log error but continue with other strategies
        
        return signals