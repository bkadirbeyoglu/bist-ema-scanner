"""
Response Schemas for API Endpoints.

These models define the structure of data returned by our API.
They map directly to the CQRS read models from Day 7.

KEY CONCEPTS:
-------------
BaseModel: Pydantic's base class that provides automatic validation,
           serialization, and JSON Schema generation. All API models
           inherit from it to get these features for free.

Field(...): Pydantic's field descriptor for adding metadata and validation.
            The "..." (Ellipsis) means "required" - no default value allowed.
            Field(None) or Field(default_value) makes a field optional.

Config class: Inner class to customize Pydantic behavior for the model.
              Common settings: from_attributes, json_schema_extra.
              
PYDANTIC V2 UPDATE: Use ConfigDict instead of inner Config class.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
import json

# REUSE existing SignalType from our domain model
# WHY: Single source of truth, no duplication, stays in sync
from trading_system.strategies.signals import SignalType


class StrategyPerformanceResponse(BaseModel):
    """
    Strategy performance metrics response.
    
    Maps to StrategyPerformance read model from Day 7 Session 2.
    
    WHY INHERIT FROM BaseModel?
    - Automatic JSON serialization/deserialization
    - Type validation (returns 422 if invalid)
    - OpenAPI schema generation (for Swagger docs)
    - IDE autocompletion and type checking
    """
    
    # PYDANTIC V2: Use ConfigDict instead of inner Config class
    model_config = ConfigDict(
        from_attributes=True,  # Enable: Model.model_validate(any_object)
        json_schema_extra={
            "example": {
                "strategy_id": "strategy-ma-001",
                "strategy_name": "MovingAverageCrossover",
                "total_signals": 1247,
                "buy_signals": 623,
                "sell_signals": 624,
                "win_rate": 0.58,
                "avg_profit": "1250.75",
                "total_profit": "779218.25",
                "sharpe_ratio": 1.85,
                "last_signal_at": "2024-01-15T14:23:00Z"
            }
        }
    )
    
    strategy_id: str = Field(
        ...,  # "..." = Required (no default value)
        description="Unique identifier for the strategy"
    )
    strategy_name: str = Field(
        ...,  # Required
        description="Name of the trading strategy"
    )
    total_signals: int = Field(
        ...,  # Required
        description="Total number of signals generated",
        ge=0  # Validation: must be >= 0
    )
    buy_signals: int = Field(..., ge=0)
    sell_signals: int = Field(..., ge=0)
    win_rate: Optional[float] = Field(
        None,  # None = Optional (default is None)
        description="Percentage of profitable signals",
        ge=0.0,
        le=1.0
    )
    avg_profit: Optional[Decimal] = Field(
        None,
        description="Average profit per winning signal"
    )
    total_profit: Optional[Decimal] = Field(
        None,
        description="Total cumulative profit"
    )
    sharpe_ratio: Optional[float] = Field(
        None,
        description="Risk-adjusted return metric"
    )
    last_signal_at: Optional[datetime] = Field(
        None,
        description="Timestamp of most recent signal"
    )
    
    @classmethod
    def from_read_model(cls, read_model) -> "StrategyPerformanceResponse":
        """
        Factory method to convert a Day 7 read model to this API response.
        
        WHAT IS @classmethod?
        - A method that receives the class (cls) instead of an instance (self)
        - Can be called on the class itself: StrategyPerformanceResponse.from_read_model(data)
        - Used for alternative constructors / factory methods
        
        WHY DO WE IMPLEMENT THIS?
        Our internal read models (from Day 7) and API responses serve different purposes:
        
        Internal Read Model (Day 7):
        - Optimized for database queries and internal processing
        - May have database-specific types (e.g., SQLAlchemy columns)
        - Field names might follow database conventions (snake_case)
        - Contains all fields, including internal ones not meant for clients
        
        API Response Model (Day 8):
        - Optimized for JSON serialization to clients
        - Uses Pydantic types with validation
        - Field names follow API conventions
        - Only exposes fields that clients should see
        - Includes OpenAPI documentation (descriptions, examples)
        
        This method acts as a TRANSLATOR between these two worlds:
        
            Database → Read Model → from_read_model() → API Response → JSON → Client
        
        It also allows us to:
        - Transform values (e.g., Decimal to float for JSON)
        - Handle None values gracefully
        - Add default values for missing fields
        - Rename fields if API conventions differ from internal ones
        
        USAGE:
            # In your endpoint:
            read_model = query_service.get_strategy_performance(strategy_id)
            return StrategyPerformanceResponse.from_read_model(read_model)
        """
        return cls(
            strategy_id=read_model.strategy_id,
            strategy_name=read_model.strategy_name,
            total_signals=read_model.total_signals,
            buy_signals=read_model.buy_signals,
            sell_signals=read_model.sell_signals,
            win_rate=float(read_model.win_rate) if read_model.win_rate else None,
            avg_profit=read_model.avg_profit,
            total_profit=read_model.total_profit,
            sharpe_ratio=float(read_model.sharpe_ratio) if read_model.sharpe_ratio else None,
            last_signal_at=read_model.last_signal_at
        )


class SignalResponse(BaseModel):
    """Individual signal details."""
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "signal_id": "sig-12345",
                "strategy_id": "strategy-ma-001",
                "symbol": "AAPL",
                "signal_type": "BUY",
                "signal_strength": 0.85,
                "price": "150.25",
                "timestamp": "2024-01-15T14:23:00Z",
                "reason": "Fast MA crossed above slow MA",
                "indicators": {"fast_ma": 149.50, "slow_ma": 148.75}
            }
        }
    )
    
    signal_id: str
    strategy_id: str
    symbol: str
    signal_type: SignalType
    signal_strength: float = Field(ge=0.0, le=1.0)
    price: Decimal
    timestamp: datetime
    reason: Optional[str] = None
    indicators: Dict[str, Any] = Field(default_factory=dict)


class BacktestMetricsResponse(BaseModel):
    """Backtest performance metrics."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_return": 24.5,
                "sharpe_ratio": 1.85,
                "max_drawdown": -12.3,
                "win_rate": 0.58,
                "total_trades": 87,
                "profit_factor": 1.85
            }
        }
    )
    
    total_return: float = Field(
        ...,
        description="Total return percentage"
    )
    sharpe_ratio: float = Field(
        ...,
        description="Risk-adjusted return metric"
    )
    max_drawdown: float = Field(
        ...,
        description="Maximum peak-to-trough decline percentage",
        le=0  # Drawdown is negative
    )
    win_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0
    )
    total_trades: int = Field(..., ge=0)
    profit_factor: Optional[float] = Field(None, ge=0)


class BacktestResponse(BaseModel):
    """
    Complete backtest run details.
    
    Maps to BacktestSummary read model from Day 7 Session 2.
    """
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "backtest_id": "e4c7a3b2-9f1d-4e8a-b6c3-2d1f8e9a7c5b",
                "strategy_name": "MovingAverageCrossover",
                "symbol": "AAPL",
                "parameters": {"fast_period": 20, "slow_period": 50},
                "metrics": {
                    "total_return": 24.5,
                    "sharpe_ratio": 1.85,
                    "max_drawdown": -12.3,
                    "win_rate": 0.58,
                    "total_trades": 87,
                    "profit_factor": 1.85
                },
                "start_date": "2023-01-01T00:00:00Z",
                "end_date": "2023-12-31T23:59:59Z",
                "completed_at": "2024-01-15T10:30:00Z"
            }
        }
    )
    
    backtest_id: str = Field(..., description="Unique backtest identifier")
    strategy_name: str
    symbol: str
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy parameters used in this run"
    )
    metrics: BacktestMetricsResponse
    start_date: datetime
    end_date: datetime
    completed_at: datetime
    
    @classmethod
    def from_read_model(cls, read_model) -> "BacktestResponse":
        """Convert Day 7 backtest read model to API response."""
        # Handle parameters - might be string (JSON) or dict
        params = read_model.parameters
        if isinstance(params, str):
            params = json.loads(params)
        
        return cls(
            backtest_id=str(read_model.backtest_id),
            strategy_name=read_model.strategy_name,
            symbol=read_model.symbol,
            parameters=params or {},
            metrics=BacktestMetricsResponse(
                total_return=float(read_model.total_return),
                sharpe_ratio=float(read_model.sharpe_ratio),
                max_drawdown=float(read_model.max_drawdown),
                win_rate=getattr(read_model, 'win_rate', None),
                total_trades=getattr(read_model, 'total_trades', 0) or 0,
                profit_factor=getattr(read_model, 'profit_factor', None)
            ),
            start_date=read_model.start_date,
            end_date=read_model.end_date,
            completed_at=read_model.completed_at
        )


class StrategyListResponse(BaseModel):
    """List of strategies with basic info."""
    strategies: List[StrategyPerformanceResponse]
    total: int = Field(..., description="Total number of strategies")


class BacktestListResponse(BaseModel):
    """List of backtest runs."""
    backtests: List[BacktestResponse]
    total: int = Field(..., description="Total number of backtests")


# Authentication responses
class TokenResponse(BaseModel):
    """JWT token response."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800
            }
        }
    )
    
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")


class ErrorResponse(BaseModel):
    """Standard error response."""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Strategy not found",
                "error_code": "STRATEGY_NOT_FOUND"
            }
        }
    )
    
    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Machine-readable error code")