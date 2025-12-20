"""
Pydantic schemas for Paper Trading API.

Uses typing.Annotated (Pydantic v2 style) for cleaner validation:
    initial_cash: Annotated[Decimal, Field(ge=1000)]
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel
from pydantic import Field


class OrderSideSchema(str, Enum):
    """Order side for API communication."""
    BUY = "BUY"
    SELL = "SELL"


class SessionStateSchema(str, Enum):
    """Session state for API responses."""
    IDLE = "IDLE"        # Created, not yet started
    RUNNING = "RUNNING"  # Actively accepting trades
    PAUSED = "PAUSED"    # Temporarily halted
    STOPPED = "STOPPED"  # Permanently terminated


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class CreateSessionRequest(BaseModel):
    """Request body for creating a new paper trading session."""
    
    initial_cash: Annotated[
        Decimal,
        Field(ge=Decimal("1000"), le=Decimal("10000000")),
    ] = Decimal("100000")
    
    slippage_bps: Annotated[
        int,
        Field(ge=0, le=100, description="Slippage in basis points (5 = 0.05%)"),
    ] = 5
    
    commission_per_share: Annotated[
        Decimal,
        Field(ge=Decimal("0"), le=Decimal("1")),
    ] = Decimal("0.005")
    
    min_commission: Annotated[
        Decimal,
        Field(ge=Decimal("0"), le=Decimal("100")),
    ] = Decimal("1.00")
    
    session_id: Annotated[
        str | None,
        Field(min_length=36, max_length=36, description="Optional UUID string"),
    ] = None


class SubmitOrderRequest(BaseModel):
    """
    Request body for submitting a manual order.
    
    Example:
        POST /api/v1/sessions/{id}/orders
        {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 100,
            "market_price": "150.00"
        }
    """
    
    symbol: Annotated[
        str,
        Field(
            min_length=1,
            max_length=10,
            pattern=r"^[A-Z]{1,5}$",  # 1-5 uppercase letters
            description="Stock ticker symbol",
            examples=["AAPL", "GOOGL", "MSFT"],
        ),
    ]
    
    side: Annotated[
        OrderSideSchema,
        Field(description="Order side: BUY or SELL"),
    ]
    
    quantity: Annotated[
        int,
        Field(
            gt=0,
            le=1000000,
            description="Number of shares to trade",
            examples=[100, 500],
        ),
    ]
    
    market_price: Annotated[
        Decimal,
        Field(
            gt=Decimal("0"),
            le=Decimal("1000000"),
            description="Current market price for the symbol",
            examples=[Decimal("150.00"), Decimal("2800.50")],
        ),
    ]


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class PositionResponse(BaseModel):
    """Response model for a single position in the portfolio."""
    
    symbol: str
    quantity: int
    entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal


class PortfolioResponse(BaseModel):
    """
    Response model for a complete portfolio snapshot.
    
    Includes cash, positions, and P&L calculations.
    """
    
    cash: Decimal
    initial_cash: Decimal
    positions_value: Decimal
    total_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    return_percent: Decimal
    positions: list[PositionResponse]


class TradeResponse(BaseModel):
    """Response model for a single executed trade."""
    
    trade_id: str
    symbol: str
    side: OrderSideSchema
    quantity: int
    price: Decimal
    total_value: Decimal
    commission: Decimal
    slippage: Decimal
    timestamp: datetime


class SessionResponse(BaseModel):
    """
    Response model for session details.
    
    Used for session creation, retrieval, and state changes.
    """
    
    session_id: str
    state: SessionStateSchema
    initial_cash: Decimal
    current_cash: Decimal
    total_value: Decimal
    trade_count: int


class SessionListResponse(BaseModel):
    """Response model for listing multiple sessions."""
    
    sessions: list[SessionResponse]
    total: int


class OrderExecutionResponse(BaseModel):
    """
    Response model for order execution result.
    
    Contains details about the executed trade or error information.
    """
    
    success: bool
    session_id: str
    trade_id: str | None = None
    symbol: str
    side: OrderSideSchema
    quantity: int
    requested_price: Decimal
    executed_price: Decimal | None = None
    slippage: Decimal | None = None
    commission: Decimal | None = None
    total_cost: Decimal | None = None
    error: str | None = None


class ErrorResponse(BaseModel):
    """Standard error response for API errors."""
    
    detail: str
    error_code: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str
    service: str
    active_sessions: int
    timestamp: datetime