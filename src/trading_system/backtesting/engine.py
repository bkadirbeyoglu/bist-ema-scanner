"""Main backtesting engine with event bus integration.

ARCHITECTURE: Facade Pattern
The BacktestEngine provides a simple interface for complex backtesting:
- Hides Backtrader complexity
- Manages event bus integration
- Coordinates data loading, strategy execution, analysis
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Type, Optional
from uuid import uuid4

import backtrader as bt
import pandas as pd

from src.trading_system.strategies.base import TradingStrategy
from src.trading_system.shared_kernel.event_bus_protocol import EventBus
from src.trading_system.shared_kernel.event_bus import InMemoryEventBus
from src.trading_system.shared_kernel.backtest_events import BacktestCompletedEvent

from src.trading_system.backtesting.data_feed import TradingSystemDataFeed, BacktestDataLoader
from src.trading_system.backtesting.strategy_adapter import StrategyAdapter
from src.trading_system.backtesting.analyzers import TradingSystemAnalyzer, DetailedTradeAnalyzer


class BacktestEngine:
    """Production-grade backtesting engine.
    
    FACADE PATTERN: Simple interface, complex implementation
    Usage:
        engine = BacktestEngine()
        metrics = await engine.run_backtest(
            strategy=MovingAverageStrategy(),
            symbol='AAPL',
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31)
        )
    
    Behind the scenes, this:
    - Loads historical data
    - Creates Backtrader cerebro
    - Adds custom data feed
    - Adapts strategy to Backtrader
    - Runs backtest
    - Collects and publishes metrics
    
    CONFIGURATION: Sensible defaults
    All parameters have defaults but can be customized.
    """
    
    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        initial_cash: float = 100000,
        commission: float = 0.001,
        slippage: float = 0.0,
    ):
        """Initialize backtesting engine.
        
        Args:
            event_bus: Event bus for publishing (creates default if None)
            initial_cash: Starting portfolio value
            commission: Commission per trade (0.001 = 0.1%)
            slippage: Slippage per trade
        """
        self.event_bus = event_bus or InMemoryEventBus()
        self.initial_cash = initial_cash
        self.commission = commission
        self.slippage = slippage
    
    async def run_backtest(
        self,
        strategy: TradingStrategy,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        plot: bool = False
    ) -> Dict[str, Any]:
        """Run complete backtest and return metrics.
        
        ORCHESTRATION: Coordinates all components
        This is the main method that brings everything together.
        
        Args:
            strategy: Our domain strategy instance
            symbol: Trading symbol (e.g., 'AAPL')
            start_date: Backtest start date
            end_date: Backtest end date
            plot: Whether to plot results
        
        Returns:
            Dictionary of performance metrics
        """
        print(f"\nStarting Backtest")
        print(f"   Strategy: {strategy.__class__.__name__}")
        print(f"   Symbol: {symbol}")
        print(f"   Period: {start_date.date()} to {end_date.date()}")
        print(f"   Initial Cash: ${self.initial_cash:,.2f}\n")
        
        # Step 1: Create Cerebro instance
        # CEREBRO: Backtrader's orchestration engine
        cerebro = bt.Cerebro()
        
        # Step 2: Load historical data
        # EXTERNAL API: Yahoo Finance
        df = BacktestDataLoader.load_yahoo_finance(symbol, start_date, end_date)
        
        # Step 3: Create our custom data feed
        # CUSTOM DATA FEED: No event publishing (simplified)
        # 
        # PYLINT SUPPRESSION: The keyword arguments below are defined in the
        # params tuple of TradingSystemDataFeed. Backtrader's metaclass converts
        # them to constructor parameters at runtime, but Pylint can't detect this.
        data = TradingSystemDataFeed(  # pylint: disable=unexpected-keyword-arg
            dataname=df,
            symbol=symbol,
            event_bus=self.event_bus
        )
        cerebro.adddata(data)
        
        # Step 4: Add strategy via adapter
        # ADAPTER PATTERN: Bridges our strategy to Backtrader
        cerebro.addstrategy(
            StrategyAdapter,
            strategy_class=type(strategy),
            event_bus=self.event_bus,
            symbol=symbol
        )
        
        # Step 5: Configure broker
        cerebro.broker.setcash(self.initial_cash)
        cerebro.broker.setcommission(commission=self.commission)
        
        # Step 6: Add analyzers
        # OBSERVER PATTERN: Analyzers watch the backtest
        cerebro.addanalyzer(TradingSystemAnalyzer, _name='trading_system')
        cerebro.addanalyzer(DetailedTradeAnalyzer, _name='detailed_trades')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # Print starting value
        start_value = cerebro.broker.getvalue()
        print(f"Starting Portfolio Value: ${start_value:,.2f}\n")
        
        # Step 7: Run backtest
        # This is synchronous - Backtrader isn't async
        print("Running backtest...\n")
        results = cerebro.run()
        
        # Get final value
        end_value = cerebro.broker.getvalue()
        
        # Step 8: Extract metrics from analyzers
        strat = results[0]
        metrics = self._extract_metrics(strat, start_value, end_value)
        
        # Step 9: Publish BacktestCompletedEvent
        await self._publish_completion_event(
            strategy, symbol, start_date, end_date, metrics
        )
        
        # Step 10: Print summary
        self._print_summary(metrics, start_value, end_value)
        
        # Step 11: Plot if requested
        if plot:
            print("\nGenerating chart...")
            cerebro.plot(style='candlestick')
        
        return metrics
    
    def _extract_metrics(
        self,
        strategy: bt.Strategy,
        start_value: float,
        end_value: float
    ) -> Dict[str, Any]:
        """Extract all metrics from analyzers.
        
        Args:
            strategy: Backtrader strategy with analyzers
            start_value: Starting portfolio value
            end_value: Ending portfolio value
        
        Returns:
            Dictionary of all metrics
        """
        # Get analyzer results
        trading_system = strategy.analyzers.trading_system.get_analysis()
        detailed = strategy.analyzers.detailed_trades.get_analysis()
        sharpe = strategy.analyzers.sharpe.get_analysis()
        returns = strategy.analyzers.returns.get_analysis()
        drawdown = strategy.analyzers.drawdown.get_analysis()
        trades = strategy.analyzers.trades.get_analysis()
        
        # Calculate additional metrics
        total_return = ((end_value - start_value) / start_value) * 100
        
        return {
            'start_value': start_value,
            'end_value': end_value,
            'total_return': total_return,
            'sharpe_ratio': sharpe.get('sharperatio', 0) or 0,
            'max_drawdown': drawdown.get('max', {}).get('drawdown', 0),
            'total_trades': trading_system.get('total_trades', 0),
            'win_rate': trading_system.get('win_rate', 0),
            'profit_factor': trading_system.get('profit_factor', 0),
            'avg_win': trading_system.get('avg_win', 0),
            'avg_loss': trading_system.get('avg_loss', 0),
            'trade_details': detailed.get('trades', []),
            'trade_statistics': detailed.get('statistics', {}),
        }
    
    async def _publish_completion_event(
        self,
        strategy: TradingStrategy,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        metrics: Dict[str, Any]
    ):
        """Publish BacktestCompletedEvent to event bus.
        
        EVENT SOURCING: Create audit trail of all backtests
        
        NOTE: The BacktestCompletedEvent dataclass expects these fields:
        - backtest_id: UUID (unique identifier for this run)
        - strategy_name: str
        - symbol: str
        - start_date: datetime
        - end_date: datetime
        - metrics: Dict[str, Any] (all performance metrics)
        
        The timestamp and event_id are inherited from BaseEvent.
        """
        backtest_id = uuid4()
        
        # DATACLASS INHERITANCE: When a dataclass inherits from another dataclass,
        # we must provide all parent fields. BaseEvent requires event_id, 
        # aggregate_id, and occurred_at.
        # pylint: disable=unexpected-keyword-arg
        event = BacktestCompletedEvent(
            event_id=uuid4(),
            aggregate_id=backtest_id,  # The backtest itself is the aggregate
            occurred_at=datetime.now(),
            backtest_id=backtest_id,
            strategy_name=strategy.__class__.__name__,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            metrics=metrics
        )
        
        await self.event_bus.publish(event)
    
    def _print_summary(
        self,
        metrics: Dict[str, Any],
        start_value: float,
        end_value: float
    ):
        """Print backtest summary.
        
        Args:
            metrics: Performance metrics
            start_value: Starting value
            end_value: Ending value
        """
        print("=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"\nPortfolio Performance:")
        print(f"  Starting Value: ${start_value:,.2f}")
        print(f"  Ending Value:   ${end_value:,.2f}")
        print(f"  Total Return:   {metrics['total_return']:.2f}%")
        
        print(f"\nRisk Metrics:")
        print(f"  Sharpe Ratio:   {metrics['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:   {metrics['max_drawdown']:.2f}%")
        
        print(f"\nTrading Metrics:")
        print(f"  Total Trades:   {metrics['total_trades']}")
        print(f"  Win Rate:       {metrics['win_rate'] * 100:.2f}%")
        print(f"  Profit Factor:  {metrics['profit_factor']:.2f}")
        print(f"  Avg Win:        ${metrics['avg_win']:.2f}")
        print(f"  Avg Loss:       ${metrics['avg_loss']:.2f}")
        print("=" * 60)