"""Adapter to use our domain strategies with Backtrader.

ARCHITECTURE: Adapter Pattern - Synchronous Version
For backtesting, strategies don't need async since there's no I/O.
Async is only needed for live trading with external APIs.

This adapter assumes strategies have SYNCHRONOUS calculate_signal() method.
"""
import backtrader as bt
import pandas as pd
from datetime import datetime

from src.trading_system.strategies.base import TradingStrategy
from src.trading_system.shared_kernel.event_bus import InMemoryEventBus


# pylint: disable=no-member
class StrategyAdapter(bt.Strategy):
    """Backtrader strategy that wraps our domain strategy.
    
    ADAPTER PATTERN: Converts Backtrader's price data to DataFrame format
    that our domain strategies expect.
    
    SYNCHRONOUS VERSION:
    - Strategies use synchronous calculate_signal() (no async)
    - Perfect for backtesting (no I/O, all in-memory)
    - Simpler code, no event loop complexity
    
    For live trading, we'll create a separate AsyncStrategyAdapter.
    
    IMPORTANT - Pylint False Positives:
    You will see Pylint warnings like:
    - "Instance of 'tuple' has no 'strategy_class' member"
    - "Instance of 'tuple' has no 'event_bus' member"
    - "Instance of 'tuple' has no 'symbol' member"
    
    These are FALSE POSITIVES. Backtrader uses a metaclass that converts
    the params tuple into instance attributes at runtime. The code works
    correctly despite these warnings.
    
    LINTER SUPPRESSION:
    The `# pylint: disable=no-member` comment on its own line above the 
    class definition suppresses these false positive warnings for the entire class.
    """
    params = (
        ('strategy_class', None),
        ('event_bus', None),
        ('symbol', 'UNKNOWN'),
    )
    
    def __init__(self):
        """Initialize adapter and domain strategy."""
        if self.params.strategy_class is None:
            raise ValueError("strategy_class parameter is required")
        
        self.event_bus = self.params.event_bus or InMemoryEventBus()
        self.domain_strategy: TradingStrategy = self.params.strategy_class(
            event_bus=self.event_bus
        )
        
        self.order = None
        
        print(f"Strategy initialized: {self.domain_strategy.__class__.__name__}")
    
    def next(self):
        """Called for each bar during backtest.
        
        BACKTRADER CALLBACK: Main trading logic
        Converts Backtrader data to DataFrame and calls domain strategy.
        
        DESIGN NOTE: This is synchronous because:
        1. Backtrader's next() callback is synchronous
        2. Backtesting has no I/O (all data in-memory)
        3. No need for async complexity here
        
        For live trading, we'll use a different adapter that handles async properly.
        """
        # Don't trade if an order is pending
        if self.order:
            return
        
        # Get enough historical data for strategy calculation
        # Most strategies need at least 50-100 bars for indicators
        lookback = max(100, getattr(self.domain_strategy, 'slow_period', 50) + 10)
        
        # Build historical data arrays
        # BACKTRADER LINES: Access historical data
        # Note: self.data.close[0] is current bar, [-1] is previous, etc.
        close_prices = []
        high_prices = []
        low_prices = []
        open_prices = []
        volumes = []
        dates = []
        
        for i in range(lookback - 1, -1, -1):
            if i <= len(self.data):
                close_prices.append(float(self.data.close[-i]))
                high_prices.append(float(self.data.high[-i]))
                low_prices.append(float(self.data.low[-i]))
                open_prices.append(float(self.data.open[-i]))
                volumes.append(float(self.data.volume[-i]) if self.data.volume[-i] else 0)
                dates.append(self.data.datetime.datetime(-i))
        
        # Need at least minimum data for strategy
        required_history = getattr(self.domain_strategy, 'get_required_history', lambda: 20)()
        if len(close_prices) < required_history:
            return
        
        # Create DataFrame in the format our strategies expect
        # PANDAS: DataFrame with OHLCV data
        market_data = pd.DataFrame({
            'close': close_prices,
            'high': high_prices,
            'low': low_prices,
            'open': open_prices,
            'volume': volumes
        }, index=dates)
        
        try:
            # Call our domain strategy (SYNCHRONOUS)
            # NO ASYNC: calculate_signal() is a regular function for backtesting
            # This keeps the code simple and avoids event loop complexity
            signal = self.domain_strategy.calculate_signal(
                market_data=market_data,
                symbol=self.params.symbol
            )
            
            # Act on signal
            # Our signals use SignalType enum with BUY, SELL, HOLD
            if signal:
                # Handle both enum and string signal types
                # PYTHON: Enums can have .value or .name attributes
                if hasattr(signal.signal_type, 'value'):
                    signal_type_str = signal.signal_type.value
                elif hasattr(signal.signal_type, 'name'):
                    signal_type_str = signal.signal_type.name
                else:
                    signal_type_str = str(signal.signal_type)
                
                if signal_type_str == 'BUY' and not self.position:
                    # Buy signal and not in position
                    size = self._calculate_position_size()
                    self.order = self.buy(size=size)
                    print(f"\n{'='*60}")
                    print(f"BUY SIGNAL: {size} shares at ${self.data.close[0]:.2f}")
                    print(f"  Date: {self.data.datetime.datetime()}")
                    print(f"  Reason: {signal.reason}")
                    print(f"  Strength: {signal.strength}")
                    if hasattr(signal, 'indicators') and signal.indicators:
                        print(f"  Indicators: {signal.indicators}")
                    print(f"{'='*60}\n")
                    
                elif signal_type_str == 'SELL' and self.position:
                    # Sell signal and in position
                    self.order = self.close()
                    print(f"\n{'='*60}")
                    print(f"SELL SIGNAL: closing position at ${self.data.close[0]:.2f}")
                    print(f"  Date: {self.data.datetime.datetime()}")
                    print(f"  Reason: {signal.reason}")
                    print(f"  Strength: {signal.strength}")
                    if hasattr(signal, 'indicators') and signal.indicators:
                        print(f"  Indicators: {signal.indicators}")
                    print(f"{'='*60}\n")
                    
        except Exception as e:
            # DEFENSIVE PROGRAMMING: Never crash the backtest
            print(f"Error in strategy: {e}")
            import traceback
            traceback.print_exc()
    
    def notify_order(self, order):
        """Called when order status changes.
        
        BACKTRADER CALLBACK: Order lifecycle tracking
        """
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f"  ✓ BUY EXECUTED: {order.executed.size} @ ${order.executed.price:.2f}")
            elif order.issell():
                print(f"  ✓ SELL EXECUTED: {order.executed.size} @ ${order.executed.price:.2f}")
            self.order = None
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"  ✗ Order {order.status}")
            self.order = None
    
    def notify_trade(self, trade):
        """Called when a trade completes (round-trip).
        
        BACKTRADER CALLBACK: Trade completed
        Called when a position is opened then closed.
        """
        if trade.isclosed:
            pnl = trade.pnlcomm
            pnl_pct = (pnl / trade.value) * 100 if trade.value else 0
            print(f"  💰 Trade P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
    
    def _calculate_position_size(self) -> int:
        """Calculate how many shares to buy.
        
        RISK MANAGEMENT: Simple position sizing
        Uses 95% of available cash for maximum capital utilization.
        
        Returns:
            Number of shares to buy
        """
        cash = self.broker.getcash() * 0.95
        price = self.data.close[0]
        size = int(cash / price)
        return max(size, 1)