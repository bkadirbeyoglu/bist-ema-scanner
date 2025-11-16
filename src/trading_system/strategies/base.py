"""Base class for all trading strategies"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional, Dict, Any
from datetime import datetime

from trading_system.strategies.signals import TradingSignal, SignalType, SignalStrength
from trading_system.contexts.portfolio_management.domain.entities.portfolio import Portfolio
from trading_system.shared_kernel.event_bus import EventBus
from trading_system.shared_kernel.events import BaseEvent


class StrategyEvent(BaseEvent):
    """Event emitted when strategy generates a signal"""
    
    def __init__(self, signal: TradingSignal):
        super().__init__()
        self.signal = signal


class TradingStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    Similar to Strategy Pattern in Java/C#:
    - Define interface for family of algorithms
    - Make them interchangeable
    - Let algorithm vary independently from clients
    """

    def __init__(self,
                 name: str,
                 event_bus: Optional[EventBus] = None,
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy.
        
        Args:
            name: Strategy identifier
            event_bus: Optional event bus for publishing signals
            config: Strategy-specific configuration
        """
        self.name = name
        self.event_bus = event_bus
        self.config = config or {}
        self.last_signal: Optional[TradingSignal] = None

    @abstractmethod
    async def calculate_signal(self,
                               market_data: pd.DataFrame,
                               symbol: str) -> TradingSignal:
        """
        Generate trading signal from market data.
        
        Args:
            market_data: DataFrame with OHLCV data and indicators
            symbol: Trading symbol
            
        Returns:
            TradingSignal with BUY/SELL/HOLD decision
        """
        pass

    @abstractmethod
    def calculate_position_size(self,
                                signal: TradingSignal,
                                portfolio: Portfolio,
                                base_size: int = 100) -> int:
        """
        Calculate position size based on signal and portfolio.
        
        Args:
            signal: Trading signal with strength
            portfolio: Current portfolio state
            base_size: Base position size (shares)
            
        Returns:
            Number of shares to trade
        """
        pass

    async def analyze_and_emit(self,
                               market_data: pd.DataFrame,
                               symbol: str) -> TradingSignal:
        """
        Analyze market data and emit signal via event bus.
        
        This is the main entry point for strategy execution.
        """
        # Generate signal
        signal = await self.calculate_signal(market_data, symbol)
        self.last_signal = signal

        # Emit event if we have event bus and actionable signal
        if self.event_bus and signal.signal_type.is_actionable():
            event = StrategyEvent(signal)
            await self.event_bus.publish(event)

        return signal
    
    def get_required_history(self) -> int:
        """
        Get number of historical periods required.
        
        Override in subclasses to specify how much
        historical data is needed for calculations.
        """
        return 50  # Default: 50 periods

    