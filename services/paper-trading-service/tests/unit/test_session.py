"""
Unit tests for Paper Trading Session.
"""

from decimal import Decimal

import pytest

from paper_trading_service.domain.session import PaperTradingSession
from paper_trading_service.domain.session import SessionState
from paper_trading_service.domain.order_simulator import OrderSide


class TestSessionLifecycle:
    """Test session state transitions."""
    
    def test_new_session_is_idle(self) -> None:
        """New sessions start IDLE."""
        session = PaperTradingSession(initial_cash=Decimal("100000"))
        assert session.state == SessionState.IDLE
    
    def test_start_transitions_to_running(self) -> None:
        """Starting moves to RUNNING."""
        session = PaperTradingSession(initial_cash=Decimal("100000"))
        session.start()
        assert session.state == SessionState.RUNNING
    
    def test_stop_transitions_to_stopped(self) -> None:
        """Stopping moves to STOPPED."""
        session = PaperTradingSession(initial_cash=Decimal("100000"))
        session.start()
        session.stop()
        assert session.state == SessionState.STOPPED
    
    def test_cannot_start_twice(self) -> None:
        """Cannot start already running session."""
        session = PaperTradingSession(initial_cash=Decimal("100000"))
        session.start()
        
        with pytest.raises(ValueError):
            session.start()


class TestSessionTrading:
    """Test trading through session."""
    
    def test_process_buy_signal(self) -> None:
        """Buy signal executes and creates position."""
        session = PaperTradingSession(initial_cash=Decimal("100000"))
        session.start()
        
        result = session.process_signal(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=Decimal("150.00"),
        )
        
        assert result.filled
        assert session.portfolio.has_position("AAPL")
    
    def test_cannot_trade_when_not_running(self) -> None:
        """Trading requires RUNNING state."""
        session = PaperTradingSession(initial_cash=Decimal("100000"))
        # Not started
        
        with pytest.raises(ValueError, match="not running"):
            session.process_signal("AAPL", OrderSide.BUY, 100, Decimal("150.00"))
    
    def test_trades_recorded_in_journal(self) -> None:
        """All trades go to journal."""
        session = PaperTradingSession(initial_cash=Decimal("100000"))
        session.start()
        
        session.process_signal("AAPL", OrderSide.BUY, 100, Decimal("150.00"))
        session.process_signal("GOOGL", OrderSide.BUY, 50, Decimal("100.00"))
        
        assert session.journal.trade_count == 2
    
    def test_sell_updates_realized_pnl(self) -> None:
        """Selling records realized P&L."""
        session = PaperTradingSession(initial_cash=Decimal("100000"))
        session.start()
        
        session.process_signal("AAPL", OrderSide.BUY, 100, Decimal("150.00"))
        session.process_signal("AAPL", OrderSide.SELL, 100, Decimal("160.00"))
        
        # Profit from $150 → $160 (minus slippage)
        assert session.portfolio.realized_pnl > Decimal("0")