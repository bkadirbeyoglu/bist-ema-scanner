"""
Tests for API schemas.

Verifies Pydantic models validate correctly.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from trading_system.api.schemas.responses import (
    StrategyPerformanceResponse,
    BacktestResponse,
)
# Import SignalType from domain model (same as responses.py uses)
from trading_system.strategies.signals import SignalType


def test_strategy_performance_validation():
    """Test StrategyPerformanceResponse validates correctly."""
    # Valid data
    valid_data = {
        "strategy_id": "strategy-test-001",
        "strategy_name": "TestStrategy",
        "total_signals": 100,
        "buy_signals": 50,
        "sell_signals": 50,
        "win_rate": 0.6,
        "avg_profit": Decimal("1000.00"),
        "total_profit": Decimal("50000.00"),
        "sharpe_ratio": 1.5,
        "last_signal_at": datetime.utcnow()
    }
    
    response = StrategyPerformanceResponse(**valid_data)
    assert response.strategy_id == "strategy-test-001"
    assert response.total_signals == 100
    assert response.win_rate == 0.6


def test_strategy_performance_validation_errors():
    """Test StrategyPerformanceResponse rejects invalid data."""
    # Negative signals (invalid)
    with pytest.raises(ValueError):
        StrategyPerformanceResponse(
            strategy_id="test",
            strategy_name="Test",
            total_signals=-1,  # Invalid: must be >= 0
            buy_signals=0,
            sell_signals=0
        )
    
    # Win rate out of range (invalid)
    with pytest.raises(ValueError):
        StrategyPerformanceResponse(
            strategy_id="test",
            strategy_name="Test",
            total_signals=100,
            buy_signals=50,
            sell_signals=50,
            win_rate=1.5  # Invalid: must be 0.0-1.0
        )


def test_signal_type_enum():
    """Test SignalType values (imported from domain model)."""
    # Note: SignalType.BUY.value == "BUY", not SignalType.BUY == "BUY"
    # because SignalType inherits from Enum, not str
    assert SignalType.BUY.value == "BUY"
    assert SignalType.SELL.value == "SELL"
    assert SignalType.HOLD.value == "HOLD"
    
    # Enum provides type safety
    valid_types = [e.value for e in SignalType]
    assert "BUY" in valid_types
    assert "INVALID" not in valid_types


def test_backtest_response_from_dict():
    """Test BacktestResponse can be created from dict."""
    data = {
        "backtest_id": "test-backtest-001",
        "strategy_name": "MovingAverage",
        "symbol": "AAPL",
        "parameters": {"fast": 20, "slow": 50},
        "metrics": {
            "total_return": 25.5,
            "sharpe_ratio": 1.8,
            "max_drawdown": -10.5,
            "win_rate": 0.65,
            "total_trades": 100,
            "profit_factor": 2.1
        },
        "start_date": "2023-01-01T00:00:00Z",
        "end_date": "2023-12-31T23:59:59Z",
        "completed_at": "2024-01-15T10:00:00Z"
    }
    
    response = BacktestResponse(**data)
    assert response.backtest_id == "test-backtest-001"
    assert response.metrics.total_return == 25.5
    assert response.metrics.sharpe_ratio == 1.8


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])