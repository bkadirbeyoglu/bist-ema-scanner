"""Moving Average Crossover Strategy Implementation"""

import pandas as pd
import numpy as np
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from trading_system.strategies.base import TradingStrategy
from trading_system.strategies.signals import (
    TradingSignal, SignalType, SignalStrength
)
from trading_system.strategies.indicators import TechnicalIndicators
from trading_system.shared_kernel.value_objects.symbol import Symbol
from trading_system.contexts.portfolio_management.domain.entities.portfolio import Portfolio


class MovingAverageCrossoverStrategy(TradingStrategy):
    """
    Classic Moving Average Crossover Strategy.
    
    Strategy Rules:
    - BUY: Fast MA crosses above Slow MA (Golden Cross)
    - SELL: Fast MA crosses below Slow MA (Death Cross)
    - HOLD: No crossover
    
    Signal Strength based on:
    - STRONG: Clear crossover with volume confirmation
    - MODERATE: Clear crossover without volume
    - WEAK: Marginal crossover
    """

    def __init__(self,
                 fast_period: int = 20,
                 slow_period: int = 50,
                 use_ema: bool = False,
                 **kwargs):
        """
        Initialize MA Crossover strategy.
        
        Args:
            fast_period: Period for fast moving average (default 20)
            slow_period: Period for slow moving average (default 50)
            use_ema: Use EMA instead of SMA (default False)
            **kwargs: Passed to parent class
        """
        super().__init__(name="MA_Crossover", **kwargs)
        
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.use_ema = use_ema
        
        # Validate periods
        if fast_period >= slow_period:
            raise ValueError("Fast period must be less than slow period")
        
        # Track previous MA values for crossover detection
        self.prev_fast_ma: Optional[float] = None
        self.prev_slow_ma: Optional[float] = None

    async def calculate_signal(self, 
                               market_data: pd.DataFrame,
                               symbol: str):
        """
        Calculate trading signal based on MA crossover.
        
        Args:
            market_data: DataFrame with at least 'close' prices
            symbol: Trading symbol
            
        Returns:
            TradingSignal with BUY/SELL/HOLD
        """
        # Ensure we have enough data
        if len(market_data) < self.slow_period:
            return TradingSignal(
                symbol=Symbol(symbol),
                signal_type=SignalType.HOLD,
                strength=SignalStrength.WEAK,
                timestamp=datetime.now(),
                strategy_name=self.name,
                reason="Insufficient data for calculation"
            )
        
        # Calculate moving averages
        if self.use_ema:
            fast_ma = TechnicalIndicators.add_ema(
                market_data, self.fast_period
            )
            slow_ma = TechnicalIndicators.add_ema(
                market_data, self.slow_period
            )
        else:
            fast_ma = TechnicalIndicators.add_sma(
                market_data, self.fast_period
            )
            slow_ma = TechnicalIndicators.add_sma(
                market_data, self.slow_period
            )
        
        # Get current and previous values
        current_fast = fast_ma.iloc[-1]
        current_slow = slow_ma.iloc[-1]
        prev_fast = fast_ma.iloc[-2] if len(fast_ma) > 1 else None
        prev_slow = slow_ma.iloc[-2] if len(slow_ma) > 1 else None
        
        # Current price for reference
        current_price = market_data['close'].iloc[-1]
        
        # Detect crossover
        signal_type = SignalType.HOLD
        reason = "No crossover detected"
        
        if prev_fast is not None and prev_slow is not None:
            # Check for golden cross (bullish)
            if prev_fast <= prev_slow and current_fast > current_slow:
                signal_type = SignalType.BUY
                reason = f"Golden Cross: {self.fast_period}-MA crossed above {self.slow_period}-MA"
            
            # Check for death cross (bearish)  
            elif prev_fast >= prev_slow and current_fast < current_slow:
                signal_type = SignalType.SELL
                reason = f"Death Cross: {self.fast_period}-MA crossed below {self.slow_period}-MA"
        
        # Calculate signal strength
        strength = self._calculate_strength(
            current_fast, current_slow, 
            market_data, signal_type
        )
        
        # Store current MA values for next iteration
        self.prev_fast_ma = current_fast
        self.prev_slow_ma = current_slow
        
        # Create signal
        return TradingSignal(
            symbol=Symbol(symbol),
            signal_type=signal_type,
            strength=strength,
            timestamp=datetime.now(),
            strategy_name=self.name,
            price=Decimal(str(current_price)),
            indicators={
                f"ma_{self.fast_period}": float(current_fast),
                f"ma_{self.slow_period}": float(current_slow),
                "crossover_spread": float(abs(current_fast - current_slow))
            },
            reason=reason
        )
    
    def _calculate_strength(self,
                           fast_ma: float,
                           slow_ma: float,
                           market_data: pd.DataFrame,
                           signal_type: SignalType) -> SignalStrength:
        """
        Calculate signal strength based on crossover clarity.
        
        Factors considered:
        - Spread between MAs (wider = stronger)
        - Volume confirmation (if available)
        - Price momentum
        """
        
        if signal_type == SignalType.HOLD:
            return SignalStrength.WEAK
        
        # Calculate spread as percentage
        spread_pct = abs(fast_ma - slow_ma) / slow_ma * 100
        
        # Check volume if available
        volume_confirmation = False
        if 'volume' in market_data.columns:
            # Volume above average?
            avg_volume = market_data['volume'].rolling(20).mean().iloc[-1]
            current_volume = market_data['volume'].iloc[-1]
            volume_confirmation = current_volume > avg_volume * 1.2
        
        # Determine strength
        if spread_pct > 2.0 and volume_confirmation:
            return SignalStrength.STRONG
        elif spread_pct > 1.0:
            return SignalStrength.MODERATE
        else:
            return SignalStrength.WEAK
    
    def calculate_position_size(self,
                               signal: TradingSignal,
                               portfolio: Portfolio,
                               base_size: int = 100) -> int:
        """
        Calculate position size using Kelly Criterion simplified.
        
        Position size factors:
        - Signal strength (multiplier)
        - Portfolio value (risk management)
        - Maximum position limit (diversification)
        """
        
        # Base position adjusted by signal strength
        strength_multiplier = signal.strength.to_position_multiplier()
        adjusted_size = int(base_size * strength_multiplier)
        
        # Risk management: Max 5% of portfolio per position
        if signal.price:
            max_position_value = float(portfolio.total_value) * 0.05
            max_shares = int(max_position_value / float(signal.price))
            adjusted_size = min(adjusted_size, max_shares)
        
        # Ensure minimum viable position
        return max(adjusted_size, 1)
    
    def get_required_history(self) -> int:
        """Get required historical periods for this strategy"""
        # Need at least slow_period + 1 for crossover detection
        return self.slow_period + 1