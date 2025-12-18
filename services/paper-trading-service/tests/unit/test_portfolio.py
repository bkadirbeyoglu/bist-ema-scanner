"""
Unit tests for Virtual Portfolio.

The portfolio is the aggregate root—all position changes go through it.
"""

from decimal import Decimal

import pytest

from paper_trading_service.domain.portfolio import VirtualPortfolio


class TestPortfolioCreation:
    """Test portfolio initialization."""
    
    def test_create_with_initial_cash(self) -> None:
        """Portfolio starts with specified cash."""
        portfolio = VirtualPortfolio(initial_cash=Decimal("100000.00"))
        
        assert portfolio.cash == Decimal("100000.00")
        assert portfolio.position_count == 0
    
    def test_each_portfolio_has_unique_id(self) -> None:
        """Portfolios have unique identifiers."""
        p1 = VirtualPortfolio(Decimal("100000"))
        p2 = VirtualPortfolio(Decimal("100000"))
        
        assert p1.id != p2.id


class TestBuying:
    """Test buying shares."""
    
    def test_buy_creates_position(self) -> None:
        """Buying creates a new position."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        
        assert portfolio.position_count == 1
        assert portfolio.has_position("AAPL")
    
    def test_buy_reduces_cash(self) -> None:
        """Buying reduces available cash."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        
        # 100,000 - (100 × 150) = 85,000
        assert portfolio.cash == Decimal("85000.00")
    
    def test_buy_more_adds_to_existing_position(self) -> None:
        """Buying same symbol adds to position."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        portfolio.buy("AAPL", 50, Decimal("160.00"))
        
        position = portfolio.get_position("AAPL")
        assert position is not None
        assert position.quantity == 150
    
    def test_cannot_buy_with_insufficient_funds(self) -> None:
        """Cannot buy if cash is insufficient."""
        portfolio = VirtualPortfolio(Decimal("1000"))
        
        with pytest.raises(ValueError, match="Insufficient"):
            portfolio.buy("AAPL", 100, Decimal("150.00"))
    
    def test_buy_symbol_case_insensitive(self) -> None:
        """Symbol lookup is case-insensitive."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        
        portfolio.buy("aapl", 100, Decimal("150.00"))
        
        assert portfolio.has_position("AAPL")
        assert portfolio.has_position("aapl")


class TestSelling:
    """Test selling shares."""
    
    def test_sell_reduces_position(self) -> None:
        """Selling reduces position quantity."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        
        portfolio.sell("AAPL", 50, Decimal("160.00"))
        
        position = portfolio.get_position("AAPL")
        assert position is not None
        assert position.quantity == 50
    
    def test_sell_increases_cash(self) -> None:
        """Selling increases cash."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        # Cash: 85,000
        
        portfolio.sell("AAPL", 50, Decimal("160.00"))
        
        # 85,000 + (50 × 160) = 93,000
        assert portfolio.cash == Decimal("93000.00")
    
    def test_sell_all_removes_position(self) -> None:
        """Selling all shares removes the position."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        
        portfolio.sell("AAPL", 100, Decimal("160.00"))
        
        assert portfolio.position_count == 0
        assert not portfolio.has_position("AAPL")
    
    def test_sell_tracks_realized_pnl(self) -> None:
        """Portfolio tracks cumulative realized P&L."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        
        portfolio.sell("AAPL", 100, Decimal("160.00"))
        
        # (160 - 150) × 100 = $1,000
        assert portfolio.realized_pnl == Decimal("1000.00")
    
    def test_cannot_sell_nonexistent_position(self) -> None:
        """Cannot sell symbol you don't own."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        
        with pytest.raises(ValueError, match="No position"):
            portfolio.sell("AAPL", 100, Decimal("150.00"))


class TestValuation:
    """Test portfolio valuation."""
    
    def test_total_value_cash_only(self) -> None:
        """Total value equals cash when no positions."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        
        assert portfolio.total_value({}) == Decimal("100000")
    
    def test_total_value_with_positions(self) -> None:
        """Total value = cash + position values."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        # Cash: 85,000
        
        prices = {"AAPL": Decimal("160.00")}
        
        # 85,000 + (100 × 160) = 101,000
        assert portfolio.total_value(prices) == Decimal("101000.00")
    
    def test_unrealized_pnl(self) -> None:
        """Calculate unrealized P&L across positions."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        portfolio.buy("GOOGL", 50, Decimal("100.00"))
        
        prices = {
            "AAPL": Decimal("160.00"),   # +$1,000
            "GOOGL": Decimal("90.00"),   # -$500
        }
        
        assert portfolio.unrealized_pnl(prices) == Decimal("500.00")


class TestSnapshot:
    """Test portfolio snapshots."""
    
    def test_snapshot_captures_state(self) -> None:
        """Snapshot includes all portfolio state."""
        portfolio = VirtualPortfolio(Decimal("100000"))
        portfolio.buy("AAPL", 100, Decimal("150.00"))
        
        prices = {"AAPL": Decimal("160.00")}
        snapshot = portfolio.snapshot(prices)
        
        assert snapshot["cash"] == Decimal("85000.00")
        assert snapshot["total_value"] == Decimal("101000.00")
        assert snapshot["unrealized_pnl"] == Decimal("1000.00")
        assert len(snapshot["positions"]) == 1