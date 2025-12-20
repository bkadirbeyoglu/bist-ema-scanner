"""
REST API Router for Paper Trading Service.

Provides endpoints for managing paper trading sessions,
executing orders, and retrieving portfolio information.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from paper_trading_service.api.schemas import CreateSessionRequest
from paper_trading_service.api.schemas import ErrorResponse
from paper_trading_service.api.schemas import HealthResponse
from paper_trading_service.api.schemas import OrderExecutionResponse
from paper_trading_service.api.schemas import OrderSideSchema
from paper_trading_service.api.schemas import PortfolioResponse
from paper_trading_service.api.schemas import PositionResponse
from paper_trading_service.api.schemas import SessionListResponse
from paper_trading_service.api.schemas import SessionResponse
from paper_trading_service.api.schemas import SessionStateSchema
from paper_trading_service.api.schemas import SubmitOrderRequest
from paper_trading_service.api.schemas import TradeResponse
from paper_trading_service.application.session_manager import SessionManager
from paper_trading_service.domain.session import OrderSide
from paper_trading_service.domain.session import SessionState


# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(prefix="/api/v1", tags=["Paper Trading"])


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

# Global session manager instance
# In production, use proper DI container (e.g., dependency-injector)
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """
    Get the global SessionManager instance.
    
    Uses lazy initialization pattern.
    
    PYTHON FEATURE: global keyword
    ──────────────────────────────
    The `global` statement tells Python that `_session_manager` refers to
    the module-level variable, not a new local variable.
    
    Without `global`:
        _session_manager = SessionManager()  # Creates LOCAL variable
        # Module-level _session_manager remains None!
    
    With `global`:
        global _session_manager
        _session_manager = SessionManager()  # Modifies MODULE variable
    
    Rule of thumb:
    - Reading a global variable: no `global` needed
    - Assigning to a global variable: `global` required
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def reset_session_manager() -> None:
    """Reset session manager (for testing)."""
    global _session_manager  # Required: we're going to set this global to None
    if _session_manager is not None:
        # Stop all sessions before reset
        for session_id in list(_session_manager.list_session_ids()):
            try:
                _session_manager.stop_session(session_id)
            except Exception:
                pass
    _session_manager = None


# PYTHON FEATURE: Annotated + Depends for Dependency Injection
# ─────────────────────────────────────────────────────────────
#
# WHY ANNOTATED? Understanding the problem it solves:
#
# 1. PYTHON'S PARAMETER ORDER RULE
#    Parameters with defaults must come AFTER parameters without:
#
#    def func(a: int = 10, b: str):  # INVALID - SyntaxError!
#    def func(b: str, a: int = 10):  # VALID
#
# 2. THE OLD FASTAPI STYLE PROBLEM
#
#    async def create_session(
#        manager: SessionManager = Depends(get_session_manager),  # Has "default"
#        request: CreateSessionRequest,  # No default - ERROR!
#    ):
#
#    Python sees `= Depends(...)` as a default value, forcing awkward ordering.
#
# 3. TYPE CHECKER CONFUSION
#
#    manager: SessionManager = Depends(get_session_manager)
#    #        ↑ declared type    ↑ actual value is Depends object!
#
#    Type checker thinks manager might be a Depends object, not SessionManager.
#    IDE autocomplete breaks - it doesn't know manager has .create_session().
#
# 4. WHAT ANNOTATED DOES
#
#    Annotated[ActualType, metadata1, metadata2, ...]
#              ↑ First arg is ALWAYS the real type (for type checkers)
#                 ↑ Everything else is metadata (ignored by type checkers)
#
# 5. HOW FASTAPI USES IT
#
#    async def create_session(
#        manager: Annotated[SessionManager, Depends(get_session_manager)],
#        request: CreateSessionRequest,
#    ):
#
#    - Python sees: Two parameters, neither has a default value ✓
#    - Type checker sees: `manager` is `SessionManager` ✓
#    - FastAPI sees: Depends() metadata → call get_session_manager() and inject
#
# 6. TYPE ALIAS FOR CLEANER CODE
#
#    Define once, use everywhere:
SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _to_session_response(
    session,  # PaperTradingSession
    prices: dict[str, Decimal] | None = None,
) -> SessionResponse:
    """Convert a PaperTradingSession to SessionResponse."""
    prices = prices or {}
    return SessionResponse(
        session_id=str(session.id),
        state=SessionStateSchema(session.state.name),
        initial_cash=session.portfolio.initial_cash,
        current_cash=session.portfolio.cash,
        total_value=session.portfolio.total_value(prices),
        trade_count=session.journal.trade_count,
    )


def _to_portfolio_response(
    session,  # PaperTradingSession
    prices: dict[str, Decimal],
) -> PortfolioResponse:
    """Convert a session's portfolio to PortfolioResponse."""
    snapshot = session.portfolio.snapshot(prices)
    
    # Build position responses
    # Note: PositionSnapshot doesn't have unrealized_pnl_percent, calculate it
    positions = []
    for pos in snapshot["positions"]:
        entry = Decimal(str(pos["entry_price"]))
        pnl = Decimal(str(pos["unrealized_pnl"]))
        cost_basis = entry * pos["quantity"]
        pnl_percent = (pnl / cost_basis * 100) if cost_basis else Decimal("0")
        
        positions.append(PositionResponse(
            symbol=pos["symbol"],
            quantity=pos["quantity"],
            entry_price=entry,
            current_price=Decimal(str(pos["current_price"])),
            market_value=Decimal(str(pos["market_value"])),
            unrealized_pnl=pnl,
            unrealized_pnl_percent=pnl_percent,
        ))
    
    return PortfolioResponse(
        cash=Decimal(str(snapshot["cash"])),
        initial_cash=session.portfolio.initial_cash,  # Get from portfolio directly
        positions_value=Decimal(str(snapshot["positions_value"])),
        total_value=Decimal(str(snapshot["total_value"])),
        unrealized_pnl=Decimal(str(snapshot["unrealized_pnl"])),
        realized_pnl=Decimal(str(snapshot["realized_pnl"])),
        total_pnl=Decimal(str(snapshot["total_pnl"])),
        return_percent=Decimal(str(snapshot["return_percent"])),
        positions=positions,
    )


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns service health status and session count.",
)
async def health_check(manager: SessionManagerDep) -> HealthResponse:
    """Check service health."""
    return HealthResponse(
        status="healthy",
        service="paper-trading-service",
        active_sessions=manager.session_count,
        timestamp=datetime.now(timezone.utc),
    )


# ============================================================================
# SESSION CRUD ENDPOINTS
# ============================================================================

@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse, "description": "Session ID already exists"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
    summary="Create a new session",
    description="Creates a new paper trading session with the specified configuration.",
)
async def create_session(
    request: CreateSessionRequest,
    manager: SessionManagerDep,
) -> SessionResponse:
    """Create a new paper trading session."""
    try:
        # Convert string session_id to UUID if provided
        session_uuid = UUID(request.session_id) if request.session_id else None
        
        session = manager.create_session(
            initial_cash=request.initial_cash,
            slippage_bps=request.slippage_bps,
            commission_per_share=request.commission_per_share,
            min_commission=request.min_commission,
            session_id=session_uuid,
        )
        return _to_session_response(session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List all sessions",
    description="Returns a list of all active paper trading sessions.",
)
async def list_sessions(manager: SessionManagerDep) -> SessionListResponse:
    """List all active sessions."""
    sessions = []
    for session_id in manager.list_session_ids():
        session = manager.get_session(session_id)
        if session:
            sessions.append(_to_session_response(session))
    
    return SessionListResponse(
        sessions=sessions,
        total=len(sessions),
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Get session details",
    description="Returns details for a specific paper trading session.",
)
async def get_session(
    session_id: str,
    manager: SessionManagerDep,
) -> SessionResponse:
    """Get session by ID."""
    session = manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    return _to_session_response(session)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Delete a session",
    description="Stops and deletes a paper trading session.",
)
async def delete_session(
    session_id: str,
    manager: SessionManagerDep,
) -> None:
    """Delete a session."""
    if not manager.delete_session(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )


# ============================================================================
# SESSION LIFECYCLE ENDPOINTS
# ============================================================================

@router.post(
    "/sessions/{session_id}/start",
    response_model=SessionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        400: {"model": ErrorResponse, "description": "Invalid state transition"},
    },
    summary="Start a session",
    description="Starts a paper trading session, enabling order execution.",
)
async def start_session(
    session_id: str,
    manager: SessionManagerDep,
) -> SessionResponse:
    """Start a session."""
    try:
        manager.start_session(session_id)
        session = manager.get_session(session_id)
        return _to_session_response(session)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/sessions/{session_id}/stop",
    response_model=SessionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        400: {"model": ErrorResponse, "description": "Invalid state transition"},
    },
    summary="Stop a session",
    description="Stops a paper trading session, disabling order execution.",
)
async def stop_session(
    session_id: str,
    manager: SessionManagerDep,
) -> SessionResponse:
    """Stop a session."""
    try:
        manager.stop_session(session_id)
        session = manager.get_session(session_id)
        return _to_session_response(session)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ============================================================================
# PORTFOLIO ENDPOINT
# ============================================================================

@router.get(
    "/sessions/{session_id}/portfolio",
    response_model=PortfolioResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Get portfolio snapshot",
    description="Returns current portfolio state including positions and P&L.",
)
async def get_portfolio(
    session_id: str,
    manager: SessionManagerDep,
) -> PortfolioResponse:
    """Get portfolio snapshot."""
    session = manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    
    # Build prices dict from positions
    # In production, you'd fetch current prices from a market data service
    # For now, use entry_price as a placeholder
    prices: dict[str, Decimal] = {}
    for symbol in session.portfolio.symbols:
        pos = session.portfolio.get_position(symbol)
        if pos:
            prices[symbol] = pos.entry_price  # Placeholder: use entry price
    
    return _to_portfolio_response(session, prices)


# ============================================================================
# ORDER ENDPOINT
# ============================================================================

@router.post(
    "/sessions/{session_id}/orders",
    response_model=OrderExecutionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        400: {"model": ErrorResponse, "description": "Order execution failed"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
    summary="Submit an order",
    description="Submits a buy or sell order for execution.",
)
async def submit_order(
    session_id: str,
    order: SubmitOrderRequest,
    manager: SessionManagerDep,
) -> OrderExecutionResponse:
    """Submit an order for execution."""
    session = manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    
    # Check session is running
    if session.state != SessionState.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is not running (state: {session.state.name})",
        )
    
    try:
        # Use manager.execute_order which calls session.process_signal
        result = manager.execute_order(
            session_id=session_id,
            symbol=order.symbol.upper(),
            side=order.side.value,  # "BUY" or "SELL"
            quantity=order.quantity,
            market_price=order.market_price,
        )
        
        return OrderExecutionResponse(
            success=result.get("success", False),
            session_id=session_id,
            trade_id=result.get("order_id"),
            symbol=order.symbol.upper(),
            side=order.side,
            quantity=order.quantity,
            requested_price=order.market_price,
            executed_price=Decimal(str(result["fill_price"])) if result.get("fill_price") else None,
            slippage=Decimal(str(result["slippage"])) if result.get("slippage") else None,
            commission=Decimal(str(result["commission"])) if result.get("commission") else None,
            total_cost=None,  # Calculate if needed
            error=result.get("rejection_reason"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ============================================================================
# TRADE HISTORY ENDPOINT
# ============================================================================

@router.get(
    "/sessions/{session_id}/trades",
    response_model=list[TradeResponse],
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Get trade history",
    description="Returns the trade history for a paper trading session.",
)
async def get_trades(
    session_id: str,
    manager: SessionManagerDep,
    limit: int = 100,
) -> list[TradeResponse]:
    """Get trade history."""
    session = manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    
    trades = []
    for trade in session.journal.get_recent(limit):
        trades.append(
            TradeResponse(
                trade_id=str(trade.trade_id),  # Convert UUID to string
                symbol=trade.symbol,
                side=(
                    OrderSideSchema.BUY
                    if trade.side == OrderSide.BUY
                    else OrderSideSchema.SELL
                ),
                quantity=trade.quantity,
                price=trade.price,
                total_value=trade.value,  # .value is the property name
                commission=trade.commission,
                slippage=trade.slippage,
                timestamp=trade.timestamp,
            )
        )
    
    return trades