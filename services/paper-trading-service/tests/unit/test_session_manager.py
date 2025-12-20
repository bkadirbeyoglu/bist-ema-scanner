"""
Unit tests for SessionManager.

Tests the session lifecycle and WeakValueDictionary behavior.
"""

import gc
import weakref
from decimal import Decimal
from typing import Generator
from uuid import UUID
from uuid import uuid4

import pytest

from paper_trading_service.application.session_manager import SessionManager
from paper_trading_service.domain.session import PaperTradingSession
from paper_trading_service.domain.session import SessionState


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def manager() -> Generator[SessionManager, None, None]:
    """
    Create a fresh SessionManager for each test.
    
    The generator pattern ensures cleanup after each test.
    """
    mgr = SessionManager()
    yield mgr
    # Cleanup: stop all sessions to release resources
    for session_id in list(mgr.list_session_ids()):
        try:
            mgr.stop_session(session_id)
        except Exception:
            pass


# ============================================================================
# SESSION CREATION TESTS
# ============================================================================

class TestSessionCreation:
    """Test creating paper trading sessions."""
    
    def test_create_session_returns_session_object(
        self, manager: SessionManager
    ) -> None:
        """Creating a session should return a PaperTradingSession."""
        session = manager.create_session(initial_cash=Decimal("100000"))
        assert isinstance(session, PaperTradingSession)
        assert session.portfolio.cash == Decimal("100000")
    
    def test_create_session_with_custom_id(
        self, manager: SessionManager
    ) -> None:
        """Should accept a custom session ID."""
        custom_id = uuid4()
        session = manager.create_session(
            initial_cash=Decimal("50000"),
            session_id=custom_id,
        )
        assert session.id == custom_id
    
    def test_create_duplicate_id_raises_error(
        self, manager: SessionManager
    ) -> None:
        """Creating a session with an existing ID should raise ValueError."""
        custom_id = uuid4()
        manager.create_session(initial_cash=Decimal("100000"), session_id=custom_id)
        with pytest.raises(ValueError, match="already exists"):
            manager.create_session(initial_cash=Decimal("100000"), session_id=custom_id)


# ============================================================================
# SESSION RETRIEVAL TESTS
# ============================================================================

class TestSessionRetrieval:
    """Test retrieving sessions from the manager."""
    
    def test_get_session_by_id(self, manager: SessionManager) -> None:
        """Should retrieve a session by its ID."""
        session = manager.create_session(initial_cash=Decimal("100000"))
        retrieved = manager.get_session(str(session.id))
        assert retrieved is session
    
    def test_get_nonexistent_session_returns_none(
        self, manager: SessionManager
    ) -> None:
        """Getting a non-existent session should return None."""
        result = manager.get_session("nonexistent-id")
        assert result is None
    
    def test_list_sessions_returns_all_ids(
        self, manager: SessionManager
    ) -> None:
        """Should list all active session IDs."""
        s1 = manager.create_session(initial_cash=Decimal("100000"))
        s2 = manager.create_session(initial_cash=Decimal("100000"))
        
        session_ids = manager.list_session_ids()
        assert len(session_ids) == 2
        assert str(s1.id) in session_ids
        assert str(s2.id) in session_ids


# ============================================================================
# SESSION LIFECYCLE TESTS
# ============================================================================

class TestSessionLifecycle:
    """Test session start/stop operations."""
    
    def test_start_session(self, manager: SessionManager) -> None:
        """Starting a session should change its state to RUNNING."""
        session = manager.create_session(initial_cash=Decimal("100000"))
        manager.start_session(str(session.id))
        assert session.state == SessionState.RUNNING
    
    def test_stop_session(self, manager: SessionManager) -> None:
        """Stopping a session should change its state to STOPPED."""
        session = manager.create_session(initial_cash=Decimal("100000"))
        manager.start_session(str(session.id))
        manager.stop_session(str(session.id))
        assert session.state == SessionState.STOPPED
    
    def test_start_nonexistent_session_raises(self, manager: SessionManager) -> None:
        """Starting a non-existent session should raise KeyError."""
        with pytest.raises(KeyError, match="not found"):
            manager.start_session("nonexistent-id")


# ============================================================================
# SESSION DELETION TESTS
# ============================================================================

class TestSessionDeletion:
    """Test session deletion."""
    
    def test_delete_session(self, manager: SessionManager) -> None:
        """Deleting a session should remove it from the manager."""
        session = manager.create_session(initial_cash=Decimal("100000"))
        session_id = str(session.id)
        result = manager.delete_session(session_id)
        assert result is True
        assert manager.get_session(session_id) is None
    
    def test_delete_nonexistent_session_returns_false(self, manager: SessionManager) -> None:
        """Deleting a non-existent session should return False."""
        assert manager.delete_session("nonexistent-id") is False
    
    def test_delete_running_session_stops_it_first(
        self, manager: SessionManager
    ) -> None:
        """Deleting a running session should stop it first."""
        session = manager.create_session(initial_cash=Decimal("100000"))
        session_id = str(session.id)
        manager.start_session(session_id)
        
        manager.delete_session(session_id)
        
        assert session.state == SessionState.STOPPED


# ============================================================================
# WEAKREF BEHAVIOR TESTS
# ============================================================================

class TestWeakRefBehavior:
    """Test WeakValueDictionary auto-cleanup behavior."""
    
    def test_manager_uses_weak_references(self, manager: SessionManager) -> None:
        """Verify SessionManager uses WeakValueDictionary internally."""
        assert isinstance(manager._weak_sessions, weakref.WeakValueDictionary)
    
    def test_released_session_can_be_garbage_collected(self, manager: SessionManager) -> None:
        """Released session should be GC'd when no strong refs remain."""
        session = manager.create_session(initial_cash=Decimal("100000"))
        session_id = str(session.id)
        
        manager.release_session(session_id)
        assert manager.get_session(session_id) is not None  # Still accessible
        
        del session
        gc.collect()
        
        assert manager.get_session(session_id) is None  # GC'd


# ============================================================================
# ORDER EXECUTION TESTS
# ============================================================================

class TestOrderExecution:
    """Test executing orders through the manager."""
    
    def test_execute_order_on_running_session(self, manager: SessionManager) -> None:
        """Should execute orders on running sessions."""
        session = manager.create_session(initial_cash=Decimal("100000"))
        session_id = str(session.id)
        manager.start_session(session_id)
        
        result = manager.execute_order(
            session_id=session_id,
            symbol="AAPL",
            side="BUY",
            quantity=100,
            market_price=Decimal("150.00"),
        )
        
        assert result["success"] is True
        assert result["symbol"] == "AAPL"
        assert result["quantity"] == 100
    
    def test_execute_order_on_nonexistent_session_raises(
        self, manager: SessionManager
    ) -> None:
        """Executing order on non-existent session should raise KeyError."""
        with pytest.raises(KeyError, match="not found"):
            manager.execute_order(
                session_id="nonexistent",
                symbol="AAPL",
                side="BUY",
                quantity=100,
                market_price=Decimal("150.00"),
            )