"""RSI Mean Reversion Strategy"""

import pandas as pd
from datetime import datetime
from decimal import Decimal

from trading_system.strategies.base import TradingStrategy
from trading_system.strategies.signals import (
    TradingSignal, SignalType, SignalStrength
)
from trading_system.strategies.indicators import TechnicalIndicators
from trading_system.shared_kernel.value_objects.symbol import Symbol
from trading_system.contexts.portfolio_management.domain.entities.portfolio import Portfolio


class RSIMeanReversionStrategy(TradingStrategy):
    """
    RSI-based Mean Reversion Strategy.
    
    Strategy Rules:
    - BUY: RSI < 30 (oversold)
    - SELL: RSI > 70 (overbought)
    - HOLD: RSI between 30-70
    
    This strategy assumes prices revert to mean after extremes.
    """

    def __init__(self,
                 rsi_period: int = 14,
                 oversold_threshold: float = 30,
                 overbought_threshold: float = 70,
                 **kwargs):
        """
        Initialize RSI strategy.
        
        Args:
            rsi_period: Period for RSI calculation (default 14)
            oversold_threshold: Buy below this RSI (default 30)
            overbought_threshold: Sell above this RSI (default 70)
        """
        super().__init__(name="RSI_MeanReversion", **kwargs)

        self.rsi_period = rsi_period
        self.oversold_threshold = oversold_threshold
        self.overbought_threshold = overbought_threshold

    def calculate_signal(self,
                        market_data: pd.DataFrame,
                        symbol: str) -> TradingSignal:
        """Generate signal based on RSI levels"""
        
        # Calculate RSI
        rsi = TechnicalIndicators.add_rsi(market_data, self.rsi_period)

        if rsi is None or len(rsi) == 0:
            return self._create_hold_signal(symbol, "Insufficient data for RSI")
        
        current_rsi = rsi.iloc[-1]
        current_price = market_data['close'].iloc[-1]

        # Determine signal
        if current_rsi < self.oversold_threshold:
            signal_type = SignalType.BUY
            reason = f"RSI {current_rsi:.1f} < {self.oversold_threshold} (oversold)"
            # Stronger signal the more oversold
            strength = (SignalStrength.STRONG if current_rsi < 20 else
                       SignalStrength.MODERATE if current_rsi < 25 else
                       SignalStrength.WEAK)
        
        elif current_rsi > self.overbought_threshold:
            signal_type = SignalType.SELL
            reason = f"RSI {current_rsi:.1f} > {self.overbought_threshold} (overbought)"
            # Stronger signal the more overbought
            strength = (SignalStrength.STRONG if current_rsi > 80 else
                       SignalStrength.MODERATE if current_rsi > 75 else
                       SignalStrength.WEAK)
        
        else:
            signal_type = SignalType.HOLD
            reason = f"RSI {current_rsi:.1f} in neutral zone"
            strength = SignalStrength.WEAK
        
        return TradingSignal(
            symbol=Symbol(symbol),
            signal_type=signal_type,
            strength=strength,
            timestamp=datetime.now(),
            strategy_name=self.name,
            price=Decimal(str(current_price)),
            indicators={"rsi": float(current_rsi)},
            reason=reason
        )
    
    def _create_hold_signal(self, symbol: str, reason: str) -> TradingSignal:
        """Helper to create HOLD signal"""
        return TradingSignal(
            symbol=Symbol(symbol),
            signal_type=SignalType.HOLD,
            strength=SignalStrength.WEAK,
            timestamp=datetime.now(),
            strategy_name=self.name,
            reason=reason
        )
    
    def calculate_position_size(self,
                               signal: TradingSignal,
                               portfolio: Portfolio,
                               base_size: int = 100) -> int:
        """
        Position sizing for mean reversion.
        
        Mean reversion typically uses smaller positions
        since we're betting against the trend.
        """
        
        # Start with conservative base for mean reversion
        conservative_base = int(base_size * 0.7)
        
        # Adjust by signal strength
        strength_multiplier = signal.strength.to_position_multiplier()
        adjusted_size = int(conservative_base * strength_multiplier)
        
        # Risk limit: Max 3% of portfolio (more conservative)
        if signal.price:
            max_position_value = float(portfolio.total_value.amount) * 0.03
            max_shares = int(max_position_value / float(signal.price))
            adjusted_size = min(adjusted_size, max_shares)
        
        return max(adjusted_size, 1)
        