"""
Unit tests for Trade Journal.
"""

from decimal import Decimal

import pytest

from paper_trading_service.domain.trade_journal import TradeJournal
from paper_trading_service.domain.trade_journal import TradeRecord
from paper_trading_service.domain.order_simulator import OrderSide


class TestRecording:
    """Test recording trades."""
    
    def test_record_trade(self) -> None:
        """Record a trade."""
        journal = TradeJournal()
        
        record = TradeRecord(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=Decimal("150.00"),
            commission=Decimal("1.00"),
        )
        journal.record(record)
        
        assert journal.trade_count == 1
    
    def test_get_recent_trades(self) -> None:
        """Get most recent trades."""
        journal = TradeJournal()
        
        for i in range(10):
            journal.record(TradeRecord(
                symbol=f"SYM{i}",
                side=OrderSide.BUY,
                quantity=100,
                price=Decimal("100.00"),
                commission=Decimal("1.00"),
            ))
        
        recent = journal.get_recent(5)
        
        assert len(recent) == 5
        assert recent[0].symbol == "SYM9"  # Most recent first


class TestBoundedHistory:
    """Test memory-bounded journal."""
    
    def test_old_entries_evicted(self) -> None:
        """Old entries removed when limit reached."""
        journal = TradeJournal(max_entries=5)
        
        for i in range(10):
            journal.record(TradeRecord(
                symbol=f"SYM{i}",
                side=OrderSide.BUY,
                quantity=100,
                price=Decimal("100.00"),
                commission=Decimal("1.00"),
            ))
        
        # Only 5 most recent kept
        assert journal.trade_count == 5
        
        all_trades = journal.get_all()
        symbols = [t.symbol for t in all_trades]
        assert "SYM0" not in symbols  # Old, evicted
        assert "SYM9" in symbols      # New, kept


class TestStatistics:
    """Test journal statistics."""
    
    def test_total_commission(self) -> None:
        """Sum of all commissions."""
        journal = TradeJournal()
        
        journal.record(TradeRecord("AAPL", OrderSide.BUY, 100, Decimal("150"), Decimal("1.50")))
        journal.record(TradeRecord("GOOGL", OrderSide.BUY, 50, Decimal("100"), Decimal("1.00")))
        
        assert journal.total_commission == Decimal("2.50")
    
    def test_total_volume(self) -> None:
        """Sum of all trade values."""
        journal = TradeJournal()
        
        journal.record(TradeRecord("AAPL", OrderSide.BUY, 100, Decimal("150"), Decimal("1")))
        journal.record(TradeRecord("GOOGL", OrderSide.SELL, 50, Decimal("100"), Decimal("1")))
        
        # 100×150 + 50×100 = 20,000
        assert journal.total_volume == Decimal("20000")
    
    def test_symbols_traded(self) -> None:
        """List unique symbols."""
        journal = TradeJournal()
        
        journal.record(TradeRecord("AAPL", OrderSide.BUY, 100, Decimal("150"), Decimal("1")))
        journal.record(TradeRecord("GOOGL", OrderSide.BUY, 50, Decimal("100"), Decimal("1")))
        journal.record(TradeRecord("AAPL", OrderSide.SELL, 50, Decimal("160"), Decimal("1")))
        
        symbols = journal.symbols_traded
        assert set(symbols) == {"AAPL", "GOOGL"}