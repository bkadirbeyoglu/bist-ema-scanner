"""Events specific to backtesting operations.

ARCHITECTURE: Domain Events for Backtest Lifecycle
These events track the backtesting process itself, separate from
trading signals or order events.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any
from uuid import UUID, uuid4

from trading_system.shared_kernel.base_event import BaseEvent


@dataclass(frozen=True)
class BacktestCompletedEvent(BaseEvent):
    """Published when a backtest completes.
    
    ARCHITECTURE: Event Sourcing Pattern
    Even backtests generate events! This allows us to:
    - Track backtest history
    - Compare strategy performance over time
    - Trigger downstream processes (reporting, notifications)
    - Maintain audit trail
    
    PYTHON FEATURE: @dataclass(frozen=True)
    Makes instances immutable - events should NEVER change after creation.
    
    DATACLASS INHERITANCE IMPORTANT NOTE:
    Since BaseEvent is frozen=True, all child classes MUST also be frozen=True.
    Python enforces this rule: "cannot inherit non-frozen dataclass from a frozen one"
    
    If BaseEvent is frozen, and you try to make BacktestCompletedEvent non-frozen,
    you'll get: TypeError: cannot inherit non-frozen dataclass from a frozen one
    
    Attributes:
        backtest_id: UUID - Unique identifier for this backtest run
        strategy_name: str - Name of the strategy tested
        symbol: str - Trading symbol used
        start_date: datetime - Backtest period start
        end_date: datetime - Backtest period end
        metrics: Dict[str, Any] - Performance metrics dictionary containing:
            - start_value: Initial portfolio value
            - end_value: Final portfolio value
            - total_return: Percentage return
            - sharpe_ratio: Risk-adjusted return
            - max_drawdown: Maximum decline from peak
            - total_trades: Number of trades executed
            - win_rate: Percentage of winning trades
            - profit_factor: Ratio of wins to losses
            - And more detailed trade statistics
    """
    
    backtest_id: UUID
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    metrics: Dict[str, Any]
    
    def __post_init__(self):
        """Ensure backtest_id is set.
        
        PYTHON: __post_init__ runs after dataclass __init__
        Since the dataclass is frozen, we use object.__setattr__
        to set the field if it wasn't provided.
        """
        if self.backtest_id is None:
            # Use object.__setattr__ because dataclass is frozen
            object.__setattr__(self, 'backtest_id', uuid4())