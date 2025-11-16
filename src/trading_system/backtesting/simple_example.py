"""Simple Backtrader example for learning.

🎓 EDUCATIONAL: Run this standalone to see basic Backtrader usage.
Then we'll build the production version with our architecture.
"""
import backtrader as bt
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


class SimpleMovingAverageCrossover(bt.Strategy):
    """Basic MA crossover strategy - Backtrader style.
    
    🏛️ ARCHITECTURE NOTE: This is a Backtrader strategy class.
    It's different from our domain strategies (MovingAverageStrategy)
    because it inherits from bt.Strategy and uses Backtrader's API.
    
    Later, we'll create an adapter to use our domain strategies instead!
    """
    
    # 🐍 PYTHON FEATURE: params tuple
    # Backtrader uses a special 'params' tuple for strategy parameters
    # This is NOT a standard Python pattern - it's Backtrader-specific
    # Backtrader's metaclass converts this tuple into attributes at runtime
    params = (
        ('fast_period', 10),
        ('slow_period', 30),
    )
    
    def __init__(self):
        """Initialize strategy with indicators.
        
        🐍 BACKTRADER PATTERN: Indicators are created in __init__
        They're automatically calculated for each bar by Backtrader.
        """
        # Create moving average indicators
        # Uses Backtrader's built-in SMA indicator
        
        # pylint: disable=no-member
        # Note: Backtrader's metaclass creates these attributes from params tuple
        # Pylint can't detect this, but they exist at runtime
        self.fast_ma = bt.indicators.SMA(
            self.data.close,
            period=self.params.fast_period  # Created by Backtrader metaclass
        )
        self.slow_ma = bt.indicators.SMA(
            self.data.close,
            period=self.params.slow_period  # Created by Backtrader metaclass
        )
        # pylint: enable=no-member
        
        # Track when we have an active order
        self.order = None
    
    def notify_order(self, order):
        """Called when order status changes.
        
        🏛️ BACKTRADER CALLBACK: This method is called automatically
        by Backtrader when orders are submitted, executed, or cancelled.
        
        🐍 PYTHON EXPLANATION: [order.Completed] syntax
        This is a list containing one element (order.Completed status).
        We use 'in' operator to check if order.status matches any status in the list.
        Using a list allows easy expansion: [order.Completed, order.Partial]
        """
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f'✅ BUY executed: Price ${order.executed.price:.2f}')
            elif order.issell():
                print(f'✅ SELL executed: Price ${order.executed.price:.2f}')
        
        # Reset order reference
        self.order = None
    
    def next(self):
        """Called for each new bar of data.
        
        🏛️ BACKTRADER CALLBACK: This is the heart of your strategy.
        It's called once for each bar in your data feed.
        
        🐍 LINES INDEXING: Remember:
        - self.data.close[0] = current bar
        - self.data.close[-1] = previous bar
        """
        # Don't trade if an order is pending
        if self.order:
            return
        
        # Check if we're in the market
        if not self.position:
            # Not in market - check for BUY signal
            # BUY when fast MA crosses above slow MA
            if self.fast_ma[0] > self.slow_ma[0] and \
               self.fast_ma[-1] <= self.slow_ma[-1]:
                print(f'📈 BUY SIGNAL at ${self.data.close[0]:.2f}')
                self.order = self.buy()
        else:
            # In market - check for SELL signal
            # SELL when fast MA crosses below slow MA
            if self.fast_ma[0] < self.slow_ma[0] and \
               self.fast_ma[-1] >= self.slow_ma[-1]:
                print(f'📉 SELL SIGNAL at ${self.data.close[0]:.2f}')
                self.order = self.sell()


def run_simple_backtest():
    """Run a simple backtest to demonstrate Backtrader basics.
    
    🎓 EDUCATIONAL: This shows the minimal Backtrader workflow:
    1. Create Cerebro
    2. Add data
    3. Add strategy
    4. Run backtest
    5. Get results
    """
    print("🚀 Running Simple Backtrader Example\n")
    
    # Step 1: Create Cerebro instance
    # 🏛️ CEREBRO: The "brain" that controls everything
    cerebro = bt.Cerebro()
    
    # Step 2: Download historical data
    # 🌐 yfinance: Free Yahoo Finance API
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)  # 1 year of data
    
    print(f"📊 Downloading AAPL data from {start_date.date()} to {end_date.date()}...")
    df = yf.download('AAPL', start=start_date, end=end_date, progress=False, auto_adjust=False)
    
    # 🔧 FIX: yfinance now returns MultiIndex columns - flatten them
    # Backtrader expects simple column names like 'Open', 'High', etc.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    
    # Verify we have data
    if df.empty:
        raise ValueError("No data downloaded - check symbol and date range")
    
    print(f"✅ Loaded {len(df)} bars of data")
    
    # Step 3: Convert pandas DataFrame to Backtrader data feed
    # 🐍 WHY CONVERT? Backtrader needs its own data format because:
    # - Backtrader uses special "Lines" objects for efficient time-series operations
    # - It needs metadata like timeframe, compression, and data naming
    # - PandasData feed handles the conversion and maintains proper indexing
    # pylint: disable=unexpected-keyword-arg
    # Note: 'dataname' is a valid Backtrader parameter, pylint doesn't recognize it
    data = bt.feeds.PandasData(dataname=df)
    # pylint: enable=unexpected-keyword-arg
    cerebro.adddata(data)
    
    # Step 4: Add strategy
    cerebro.addstrategy(SimpleMovingAverageCrossover)
    
    # Step 5: Set initial capital and commission
    cerebro.broker.setcash(100000.0)  # $100,000 starting cash
    cerebro.broker.setcommission(commission=0.001)  # 0.1% commission
    
    # Step 6: Add analyzers for performance metrics
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    
    # Step 7: Run backtest
    print(f"\n💰 Starting Portfolio Value: ${cerebro.broker.getvalue():,.2f}\n")
    results = cerebro.run()
    strat = results[0]
    
    # Step 8: Display results
    print(f"\n💰 Final Portfolio Value: ${cerebro.broker.getvalue():,.2f}")
    print(f"📊 Return: {(cerebro.broker.getvalue() / 100000 - 1) * 100:.2f}%")
    
    # Get analyzer results
    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    
    print(f"\n📈 Performance Metrics:")
    print(f"   Sharpe Ratio: {sharpe.get('sharperatio', 'N/A')}")
    print(f"   Max Drawdown: {drawdown.get('max', {}).get('drawdown', 'N/A'):.2f}%")
    
    # Optional: Plot results
    # cerebro.plot()


if __name__ == '__main__':
    run_simple_backtest()