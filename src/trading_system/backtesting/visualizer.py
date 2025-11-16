"""Professional backtest visualization tools.

ARCHITECTURE: Presentation Layer
Separates visualization from calculation.
Analyzers calculate metrics, visualizer displays them.
"""
from datetime import datetime
from typing import Dict, Any, List
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np


class BacktestVisualizer:
    """Create professional backtest charts.
    
    SEPARATION OF CONCERNS:
    - Analyzers calculate metrics
    - Visualizer presents them
    
    PYTHON: matplotlib for publication-quality charts
    """
    
    @staticmethod
    def create_performance_report(
        metrics: Dict[str, Any],
        trade_history: List[Dict[str, Any]],
        symbol: str,
        strategy_name: str
    ):
        """Create comprehensive performance report.
        
        PYTHON: GridSpec for complex subplot layouts
        
        Args:
            metrics: Performance metrics from backtest
            trade_history: List of individual trades
            symbol: Trading symbol
            strategy_name: Name of strategy
        """
        # Create figure with subplots
        # MATPLOTLIB: GridSpec allows flexible subplot layout
        fig = plt.figure(figsize=(16, 12))
        gs = GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.3)
        
        # Title
        fig.suptitle(
            f'Backtest Results: {strategy_name} on {symbol}',
            fontsize=16,
            fontweight='bold'
        )
        
        # 1. Equity Curve (top, full width)
        ax1 = fig.add_subplot(gs[0, :])
        BacktestVisualizer._plot_equity_curve(ax1, trade_history, metrics)
        
        # 2. Trade Distribution
        ax2 = fig.add_subplot(gs[1, 0])
        BacktestVisualizer._plot_trade_distribution(ax2, trade_history)
        
        # 3. Monthly Returns
        ax3 = fig.add_subplot(gs[1, 1])
        BacktestVisualizer._plot_monthly_returns(ax3, trade_history)
        
        # 4. Performance Metrics Table
        ax4 = fig.add_subplot(gs[2, 0])
        BacktestVisualizer._plot_metrics_table(ax4, metrics)
        
        # 5. Trade Statistics
        ax5 = fig.add_subplot(gs[2, 1])
        BacktestVisualizer._plot_trade_stats(ax5, metrics)
        
        plt.tight_layout()
        return fig
    
    @staticmethod
    def _plot_equity_curve(ax, trade_history: List[Dict], metrics: Dict):
        """Plot portfolio value over time."""
        if not trade_history:
            ax.text(0.5, 0.5, 'No trades executed', ha='center', va='center')
            ax.set_title('Equity Curve')
            return
        
        # Calculate cumulative P&L
        # NUMPY: cumsum for cumulative sum
        pnls = [t['pnl'] for t in trade_history]
        cumulative_pnl = np.cumsum([0] + pnls)  # Start from 0
        
        # Calculate equity
        start_value = metrics['start_value']
        equity = start_value + cumulative_pnl
        
        # Plot
        # MATPLOTLIB: plot() creates line chart
        ax.plot(equity, linewidth=2, label='Portfolio Value')
        ax.axhline(y=start_value, color='gray', linestyle='--', alpha=0.5, label='Starting Value')
        
        ax.set_title('Equity Curve', fontsize=12, fontweight='bold')
        ax.set_xlabel('Trade Number')
        ax.set_ylabel('Portfolio Value ($)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Format y-axis as currency
        # PYTHON: lambda for inline function
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    @staticmethod
    def _plot_trade_distribution(ax, trade_history: List[Dict]):
        """Plot distribution of trade P&Ls."""
        if not trade_history:
            ax.text(0.5, 0.5, 'No trades', ha='center', va='center')
            ax.set_title('Trade P&L Distribution')
            return
        
        pnls = [t['pnl'] for t in trade_history]
        
        # MATPLOTLIB: hist() creates histogram
        ax.hist(pnls, bins=20, edgecolor='black', alpha=0.7)
        ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even')
        
        ax.set_title('Trade P&L Distribution', fontsize=12, fontweight='bold')
        ax.set_xlabel('Profit/Loss ($)')
        ax.set_ylabel('Number of Trades')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
    
    @staticmethod
    def _plot_monthly_returns(ax, trade_history: List[Dict]):
        """Plot monthly returns."""
        if not trade_history:
            ax.text(0.5, 0.5, 'No trades', ha='center', va='center')
            ax.set_title('Monthly Returns')
            return
        
        # Group by month
        # PYTHON: defaultdict for automatic initialization
        from collections import defaultdict
        monthly_pnl = defaultdict(float)
        
        for trade in trade_history:
            # Extract month from exit date
            month = trade['exit_date'].strftime('%Y-%m')
            monthly_pnl[month] += trade['pnl']
        
        # Sort by month
        months = sorted(monthly_pnl.keys())
        returns = [monthly_pnl[m] for m in months]
        
        # Create bar chart
        colors = ['green' if r > 0 else 'red' for r in returns]
        ax.bar(range(len(returns)), returns, color=colors, alpha=0.7)
        
        ax.set_title('Monthly Returns', fontsize=12, fontweight='bold')
        ax.set_xlabel('Month')
        ax.set_ylabel('Return ($)')
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(months, rotation=45, ha='right')
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.grid(True, alpha=0.3, axis='y')
    
    @staticmethod
    def _plot_metrics_table(ax, metrics: Dict):
        """Display key metrics in table format."""
        ax.axis('off')
        
        # Prepare data
        table_data = [
            ['Metric', 'Value'],
            ['Total Return', f"{metrics['total_return']:.2f}%"],
            ['Sharpe Ratio', f"{metrics['sharpe_ratio']:.2f}"],
            ['Max Drawdown', f"{metrics['max_drawdown']:.2f}%"],
            ['Total Trades', f"{metrics['total_trades']}"],
            ['Win Rate', f"{metrics['win_rate'] * 100:.2f}%"],
            ['Profit Factor', f"{metrics['profit_factor']:.2f}"],
        ]
        
        # Create table
        # MATPLOTLIB: table() creates formatted table
        table = ax.table(
            cellText=table_data,
            cellLoc='left',
            loc='center',
            colWidths=[0.6, 0.4]
        )
        
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)
        
        # Style header row
        for i in range(2):
            table[(0, i)].set_facecolor('#4CAF50')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        ax.set_title('Performance Metrics', fontsize=12, fontweight='bold', pad=20)
    
    @staticmethod
    def _plot_trade_stats(ax, metrics: Dict):
        """Display trade statistics."""
        ax.axis('off')
        
        stats = metrics.get('trade_statistics', {})
        
        table_data = [
            ['Statistic', 'Value'],
            ['Avg P&L', f"${stats.get('avg_pnl', 0):.2f}"],
            ['Median P&L', f"${stats.get('median_pnl', 0):.2f}"],
            ['Std Dev P&L', f"${stats.get('std_pnl', 0):.2f}"],
            ['Best Trade', f"${stats.get('max_pnl', 0):.2f}"],
            ['Worst Trade', f"${stats.get('min_pnl', 0):.2f}"],
            ['Avg Duration', f"{stats.get('avg_duration', 0):.1f} days"],
        ]
        
        table = ax.table(
            cellText=table_data,
            cellLoc='left',
            loc='center',
            colWidths=[0.6, 0.4]
        )
        
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)
        
        # Style header
        for i in range(2):
            table[(0, i)].set_facecolor('#2196F3')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        ax.set_title('Trade Statistics', fontsize=12, fontweight='bold', pad=20)