"""Events specific to backtesting operations.

ARCHITECTURE: Domain Events for Backtest Lifecycle
These events track the backtesting process itself, separate from
trading signals or order events.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, ClassVar
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
    When inheriting from BaseEvent (which has fields with defaults),
    ALL fields in this class must also have defaults.
    
    Attributes:
        backtest_id: UUID - Unique identifier for this backtest run
        strategy_name: str - Name of the strategy tested
        symbol: str - Trading symbol used
        start_date: datetime - Backtest period start
        end_date: datetime - Backtest period end
        metrics: Dict[str, Any] - Performance metrics dictionary
        aggregate_type: str - Categorizes as Backtest event
        version: int - Event version for event store
    """
    
    # ALL FIELDS MUST HAVE DEFAULTS (because BaseEvent has defaults)
    backtest_id: UUID = field(default_factory=uuid4)  # Auto-generate if not provided
    strategy_name: str = ""
    symbol: str = ""
    start_date: datetime = field(default_factory=datetime.utcnow)
    end_date: datetime = field(default_factory=datetime.utcnow)
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Event sourcing metadata
    aggregate_type: str = "Backtest"
    version: int = 0
    
    # Class variable for event routing
    event_name: ClassVar[str] = "backtest_completed"
    
    @classmethod
    def create(
        cls,
        strategy_name: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        metrics: Dict[str, Any],
        backtest_id: UUID = None,
        **kwargs
    ) -> 'BacktestCompletedEvent':
        """
        Factory method to create BacktestCompletedEvent.
        
        This is the RECOMMENDED way to create backtest events.
        
        Args:
            strategy_name: Name of the strategy tested
            symbol: Trading symbol
            start_date: Backtest start date
            end_date: Backtest end date
            metrics: Performance metrics dictionary
            backtest_id: Optional UUID (auto-generated if not provided)
            **kwargs: Additional fields
        
        Returns:
            New BacktestCompletedEvent instance
        
        Example:
            event = BacktestCompletedEvent.create(
                strategy_name="MovingAverage",
                symbol="AAPL",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 12, 31),
                metrics={
                    "total_return": 15.5,
                    "sharpe_ratio": 1.2,
                    "max_drawdown": -8.3,
                    "total_trades": 50
                }
            )
        """
        # Generate backtest_id if not provided
        if backtest_id is None:
            backtest_id = uuid4()
        
        # Generate aggregate_id
        aggregate_id = kwargs.pop('aggregate_id', f"backtest-{backtest_id}")
        
        # Call parent factory method
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type="Backtest",
            backtest_id=backtest_id,
            strategy_name=strategy_name,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            **kwargs
        )
    
    def __post_init__(self):
        """
        Validate backtest data after initialization.
        
        Note: No need to set backtest_id here anymore - it has a default_factory.
        """
        if not self.strategy_name:
            raise ValueError("strategy_name is required")
        if not self.symbol:
            raise ValueError("symbol is required")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be after start_date")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            **super().to_dict(),
            "backtest_id": str(self.backtest_id),
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "metrics": self.metrics,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "BacktestCompletedEvent":
        """Reconstruct event from dictionary."""
        return cls(
            event_id=data["event_id"],
            aggregate_id=data["aggregate_id"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            backtest_id=UUID(data["backtest_id"]),
            strategy_name=data.get("strategy_name", ""),
            symbol=data.get("symbol", ""),
            start_date=datetime.fromisoformat(data.get("start_date", datetime.utcnow().isoformat())),
            end_date=datetime.fromisoformat(data.get("end_date", datetime.utcnow().isoformat())),
            metrics=data.get("metrics", {}),
            aggregate_type=data.get("aggregate_type", "Backtest"),
            version=data.get("version", 0)
        )