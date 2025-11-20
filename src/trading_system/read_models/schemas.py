"""
Read Model Schemas for Trading System.

These are DENORMALIZED views optimized for queries.
Different from domain models - focused on read performance.

KEY DIFFERENCES from Domain Models:
- Pre-calculated values (no computation during queries)
- Denormalized (data from multiple sources combined)
- Query-optimized indexes
- Eventually consistent (updated by projections)
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List
from enum import Enum


class StrategyStatus(Enum):
    """Strategy operational status."""
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


# ============================================
# STRATEGY PERFORMANCE READ MODEL
# ============================================

@dataclass
class StrategyPerformance:
    """
    Pre-calculated strategy performance metrics.
    
    PURPOSE:
    Dashboard can query this single row instead of processing
    thousands of SignalGeneratedEvents.
    
    UPDATED BY: SignalProjection (when signals are generated)
    QUERIED BY: Strategy dashboard, performance reports
    """
    strategy_id: str                        # "strategy-ma-AAPL"
    strategy_name: str                      # "MovingAverage"
    symbol: str                             # "AAPL"
    status: StrategyStatus                  # ACTIVE, PAUSED, STOPPED
    
    # Signal Metrics (Pre-calculated)
    total_signals: int                      # All signals generated
    buy_signals: int                        # BUY signals
    sell_signals: int                       # SELL signals
    hold_signals: int                       # HOLD signals
    
    # Performance Metrics (Pre-calculated)
    winning_signals: int                    # Profitable signals
    losing_signals: int                     # Unprofitable signals
    win_rate: Decimal                       # winning / total * 100
    avg_profit_per_signal: Decimal          # Average profit
    total_profit: Decimal                   # Sum of all profits
    max_profit: Decimal                     # Best signal
    max_loss: Decimal                       # Worst signal
    
    # Technical Metrics (Pre-calculated)
    avg_signal_strength: Decimal            # Average confidence
    sharpe_ratio: Optional[Decimal]         # Risk-adjusted return
    
    # Timestamps
    first_signal_time: Optional[datetime]   # When strategy started
    last_signal_time: Optional[datetime]    # Most recent signal
    last_updated: datetime                  # When projection ran
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for database storage."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "status": self.status.value,
            "total_signals": self.total_signals,
            "buy_signals": self.buy_signals,
            "sell_signals": self.sell_signals,
            "hold_signals": self.hold_signals,
            "winning_signals": self.winning_signals,
            "losing_signals": self.losing_signals,
            "win_rate": float(self.win_rate),
            "avg_profit_per_signal": float(self.avg_profit_per_signal),
            "total_profit": float(self.total_profit),
            "max_profit": float(self.max_profit),
            "max_loss": float(self.max_loss),
            "avg_signal_strength": float(self.avg_signal_strength),
            "sharpe_ratio": float(self.sharpe_ratio) if self.sharpe_ratio else None,
            "first_signal_time": self.first_signal_time.isoformat() if self.first_signal_time else None,
            "last_signal_time": self.last_signal_time.isoformat() if self.last_signal_time else None,
            "last_updated": self.last_updated.isoformat()
        }


# ============================================
# SIGNAL ANALYTICS READ MODEL
# ============================================

@dataclass
class SignalAnalytics:
    """
    Detailed signal information for charting and analysis.
    
    PURPOSE:
    Time-series data for charts showing signal performance over time.
    Each row represents one trading signal.
    
    UPDATED BY: SignalProjection (one row per signal)
    QUERIED BY: Performance charts, backtesting analysis
    """
    signal_id: str                          # Unique signal ID
    strategy_id: str                        # Which strategy?
    symbol: str                             # Which asset?
    signal_type: str                        # "BUY", "SELL", "HOLD"
    signal_strength: Decimal                # Confidence (0.0 - 1.0)
    
    # Signal Context
    price_at_signal: Decimal                # Market price when generated
    indicators: Dict[str, float]            # All indicator values
    reason: str                             # Why this signal?
    
    # Outcome (if known)
    actual_profit: Optional[Decimal]        # Actual profit/loss
    was_profitable: Optional[bool]          # True/False/None
    
    # Timing
    signal_time: datetime                   # When signal generated
    last_updated: datetime


# ============================================
# BACKTEST SUMMARY READ MODEL
# ============================================

@dataclass
class BacktestSummary:
    """
    Summary of backtest results for quick comparison.
    
    PURPOSE:
    Compare different strategy configurations without
    reprocessing all backtest events.
    
    UPDATED BY: BacktestProjection
    QUERIED BY: Backtest comparison reports
    """
    backtest_id: str                        # Unique backtest run
    strategy_name: str                      # Which strategy?
    symbol: str                             # Which asset?
    
    # Parameters
    parameters: Dict[str, any]              # Strategy config
    
    # Performance
    total_return: Decimal                   # Overall return %
    sharpe_ratio: Decimal                   # Risk-adjusted
    max_drawdown: Decimal                   # Worst decline
    
    # Timing
    start_date: datetime
    end_date: datetime
    completed_at: datetime
    last_updated: datetime

# ============================================
# DAILY PERFORMANCE READ MODEL
# ============================================

@dataclass
class DailyPerformance:
    """
    Daily aggregated metrics for trend analysis.
    
    PURPOSE:
    Show strategy performance trends over time.
    One row per strategy per day.
    
    UPDATED BY: DailyAggregationJob (runs end of day)
    QUERIED BY: Performance trend charts
    """
    strategy_id: str
    date: str                               # YYYY-MM-DD
    
    # Daily Metrics
    signals_generated: int
    winning_signals: int
    losing_signals: int
    daily_profit: Decimal
    win_rate: Decimal
    
    # Timestamps
    last_updated: datetime