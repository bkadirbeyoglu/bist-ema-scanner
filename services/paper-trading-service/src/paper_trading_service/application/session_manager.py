"""
Session Manager for Paper Trading.

Manages multiple paper trading sessions with automatic cleanup
using WeakValueDictionary for abandoned session garbage collection.
"""

from __future__ import annotations

import weakref
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

from paper_trading_service.domain.session import OrderSide
from paper_trading_service.domain.session import PaperTradingSession
from paper_trading_service.domain.session import SessionConfig
from paper_trading_service.domain.session import SessionState


class SessionManager:
    """
    Manages paper trading sessions with automatic cleanup.
    
    Uses two dictionaries:
    - _active_sessions: Strong refs to sessions we want to keep
    - _weak_sessions: Weak refs for lookup without preventing GC
    
    Call release_session() to make a session eligible for GC.
    """
    
    def __init__(self) -> None:
        """Initialize with strong and weak storage."""
        self._active_sessions: dict[str, PaperTradingSession] = {}
        self._weak_sessions: weakref.WeakValueDictionary[str, PaperTradingSession] = (
            weakref.WeakValueDictionary()
        )
    
    # ========================================================================
    # SESSION CREATION
    # ========================================================================
    
    def create_session(
        self,
        initial_cash: Decimal = Decimal("100000.00"),
        slippage_bps: int = 5,
        commission_per_share: Decimal = Decimal("0.005"),
        min_commission: Decimal = Decimal("1.00"),
        session_id: UUID | None = None,
    ) -> PaperTradingSession:
        """
        Create a new paper trading session.
        
        Args:
            initial_cash: Starting cash balance (default: $100,000)
            slippage_bps: Slippage in basis points (default: 5 = 0.05%)
            commission_per_share: Commission per share (default: $0.005)
            min_commission: Minimum commission per trade (default: $1.00)
            session_id: Optional custom UUID; generated if not provided
        
        Returns:
            The newly created PaperTradingSession
        
        Raises:
            ValueError: If session_id already exists
        """
        # Generate ID if not provided
        if session_id is None:
            session_id = uuid4()
        
        session_id_str = str(session_id)
        
        # Check for duplicates in both dictionaries
        if session_id_str in self._active_sessions or session_id_str in self._weak_sessions:
            raise ValueError(f"Session '{session_id_str}' already exists")
        
        # Create config and session
        config = SessionConfig(
            initial_cash=initial_cash,
            slippage_bps=slippage_bps,
            commission_per_share=commission_per_share,
            min_commission=min_commission,
        )
        
        session = PaperTradingSession(
            initial_cash=initial_cash,
            config=config,
            session_id=session_id,
        )
        
        # Store in both dictionaries (using string key for consistency)
        self._active_sessions[session_id_str] = session
        self._weak_sessions[session_id_str] = session
        
        return session
    
    # ========================================================================
    # SESSION RETRIEVAL
    # ========================================================================
    
    def get_session(self, session_id: str) -> PaperTradingSession | None:
        """
        Get a session by ID.
        
        Checks both active and weak references.
        
        Args:
            session_id: The session identifier
        
        Returns:
            The session if found, None otherwise
        """
        # Check active sessions first (strong refs)
        session = self._active_sessions.get(session_id)
        if session is not None:
            return session
        
        # Fall back to weak refs (might return None if GC'd)
        return self._weak_sessions.get(session_id)
    
    def list_session_ids(self) -> list[str]:
        """
        List all session IDs (both active and weak).
        
        Returns:
            List of session IDs currently accessible
        """
        # Combine both sets of IDs
        all_ids = set(self._active_sessions.keys()) | set(self._weak_sessions.keys())
        return list(all_ids)
    
    @property
    def session_count(self) -> int:
        """Get the total number of accessible sessions."""
        return len(self.list_session_ids())
    
    # ========================================================================
    # SESSION LIFECYCLE
    # ========================================================================
    
    def start_session(self, session_id: str) -> None:
        """
        Start a session (enable order execution).
        
        Args:
            session_id: The session identifier
        
        Raises:
            KeyError: If session not found
            ValueError: If session cannot be started (wrong state)
        """
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        session.start()
    
    def stop_session(self, session_id: str) -> None:
        """
        Stop a session (disable order execution).
        
        Args:
            session_id: The session identifier
        
        Raises:
            KeyError: If session not found
        """
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        session.stop()
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session completely.
        
        Stops the session if running, then removes from manager.
        
        Args:
            session_id: The session identifier
        
        Returns:
            True if deleted, False if not found
        """
        session = self.get_session(session_id)
        if session is None:
            return False
        
        # Stop if running
        if session.state == SessionState.RUNNING:
            session.stop()
        
        # Remove from both dictionaries
        self._active_sessions.pop(session_id, None)
        # Note: Weak ref will be auto-removed when session is GC'd
        # but we can explicitly remove it too for immediate cleanup
        try:
            del self._weak_sessions[session_id]
        except KeyError:
            pass
        
        return True
    
    def release_session(self, session_id: str) -> bool:
        """
        Release a session for garbage collection.
        
        The session remains accessible via get_session() as long as
        other code holds references to it. Once all external references
        are gone, the garbage collector will clean it up automatically.
        
        Use this for sessions that users have abandoned but might
        still be referenced by other parts of the system.
        
        Args:
            session_id: The session identifier
        
        Returns:
            True if released, False if not found in active sessions
        
        Example:
            >>> manager.release_session("user-123-session")
            >>> # Session still accessible if other code references it
            >>> # GC will clean up when all references are gone
        """
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            # Session stays in _weak_sessions for lookup
            return True
        return False
    
    # ========================================================================
    # ORDER EXECUTION
    # ========================================================================
    
    def execute_order(
        self,
        session_id: str,
        symbol: str,
        side: str,
        quantity: int,
        market_price: Decimal,
    ) -> dict:
        """
        Execute an order on a session.
        
        Args:
            session_id: Target session ID
            symbol: Stock symbol (e.g., "AAPL")
            side: "BUY" or "SELL"
            quantity: Number of shares
            market_price: Current market price
        
        Returns:
            Execution result dictionary with success status and details
        
        Raises:
            KeyError: If session not found
            ValueError: If session not running or invalid order
        """
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        
        order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
        
        # Call process_signal which returns OrderResult
        result = session.process_signal(
            symbol=symbol.upper(),
            side=order_side,
            quantity=quantity,
            price=market_price,
        )
        
        # Convert OrderResult to dict
        return {
            "success": result.filled,
            "order_id": str(result.order_id),
            "symbol": result.symbol,
            "side": result.side.name,
            "quantity": result.quantity,
            "fill_price": float(result.fill_price) if result.fill_price else None,
            "slippage": float(result.slippage),
            "commission": float(result.commission),
            "timestamp": result.timestamp.isoformat(),
            "rejection_reason": result.rejection_reason,
        }
    
    # ========================================================================
    # SESSION SUMMARIES
    # ========================================================================
    
    def get_session_summary(self, session_id: str) -> dict | None:
        """
        Get a summary of a session's state.
        
        Args:
            session_id: The session identifier
        
        Returns:
            Summary dictionary or None if not found
        """
        session = self.get_session(session_id)
        if session is None:
            return None
        
        return {
            "session_id": str(session.id),
            "state": session.state.name,
            "initial_cash": float(session.portfolio.initial_cash),
            "current_cash": float(session.portfolio.cash),
            "total_value": float(session.portfolio.total_value({})),
            "trade_count": session.journal.trade_count,
        }
    
    def get_all_summaries(self) -> list[dict]:
        """Get summaries for all accessible sessions."""
        summaries = []
        for session_id in self.list_session_ids():
            summary = self.get_session_summary(session_id)
            if summary:
                summaries.append(summary)
        return summaries