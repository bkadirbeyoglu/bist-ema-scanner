"""Command-line tool for running backtests quickly.

CONVENIENCE: Run backtests without writing code
Usage:
    poetry run python scripts/run_backtest.py -s MA --symbol AAPL --days 90
    poetry run python scripts/run_backtest.py -s RSI --symbol TSLA --plot
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path
# This allows imports to work regardless of where the script is run from
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.trading_system.strategies.moving_average import MovingAverageCrossoverStrategy
from src.trading_system.strategies.rsi_strategy import RSIMeanReversionStrategy
from src.trading_system.backtesting.engine import BacktestEngine
from src.trading_system.backtesting.visualizer import BacktestVisualizer


# Map strategy names to classes
STRATEGIES = {
    'MA': MovingAverageCrossoverStrategy,
    'RSI': RSIMeanReversionStrategy,
}


async def main():
    """Main entry point for backtest runner."""
    # Parse command-line arguments
    # PYTHON: argparse for professional CLI
    parser = argparse.ArgumentParser(
        description='Run backtest on trading strategy'
    )
    
    parser.add_argument(
        '-s', '--strategy',
        choices=list(STRATEGIES.keys()),
        required=True,
        help='Strategy to test'
    )
    
    parser.add_argument(
        '--symbol',
        default='AAPL',
        help='Trading symbol (default: AAPL)'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=365,
        help='Number of days to backtest (default: 365)'
    )
    
    parser.add_argument(
        '--initial-cash',
        type=float,
        default=100000,
        help='Initial capital (default: 100000)'
    )
    
    parser.add_argument(
        '--plot',
        action='store_true',
        help='Show performance chart'
    )
    
    args = parser.parse_args()
    
    # Create strategy
    strategy_class = STRATEGIES[args.strategy]
    strategy = strategy_class()
    
    # Calculate dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    # Create engine
    engine = BacktestEngine(initial_cash=args.initial_cash)
    
    # Run backtest
    print(f"\nRunning {args.strategy} strategy on {args.symbol}")
    print(f"Period: {start_date.date()} to {end_date.date()}\n")
    
    metrics = await engine.run_backtest(
        strategy=strategy,
        symbol=args.symbol,
        start_date=start_date,
        end_date=end_date,
        plot=args.plot
    )
    
    # Generate visualization
    if args.plot and metrics['total_trades'] > 0:
        trade_history = metrics['trade_details']
        
        fig = BacktestVisualizer.create_performance_report(
            metrics=metrics,
            trade_history=trade_history,
            symbol=args.symbol,
            strategy_name=strategy_class.__name__
        )
        
        import matplotlib.pyplot as plt
        plt.show()


if __name__ == '__main__':
    # Run async main
    # PYTHON: asyncio.run() is the entry point for async programs
    asyncio.run(main())