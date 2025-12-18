"""
Unit tests for Position entity.

TDD: These tests define expected behavior BEFORE implementation.
"""

from decimal import Decimal

import pytest

from paper_trading_service.domain.position import Position
from paper_trading_service.domain.position import PositionSide


class TestPositionCreation:
    """Test creating positions."""
    
    def test_create_long_position(self) -> None:
        """Create a basic long position."""
        position = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=Decimal("150.00"),
        )
        
        assert position.symbol == "AAPL"
        assert position.quantity == 100
        assert position.entry_price == Decimal("150.00")
        assert position.side == PositionSide.LONG
    
    def test_symbol_normalized_to_uppercase(self) -> None:
        """Symbols are always uppercase."""
        position = Position("aapl", 100, Decimal("150.00"))
        assert position.symbol == "AAPL"
    
    def test_position_requires_positive_quantity(self) -> None:
        """Quantity must be positive."""
        with pytest.raises(ValueError, match="positive"):
            Position("AAPL", 0, Decimal("150.00"))
    
    def test_position_requires_positive_price(self) -> None:
        """Entry price must be positive."""
        with pytest.raises(ValueError, match="positive"):
            Position("AAPL", 100, Decimal("0"))


class TestPositionPnL:
    """Test P&L calculations."""
    
    def test_unrealized_pnl_profit(self) -> None:
        """Unrealized P&L when price increases."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        pnl = position.unrealized_pnl(current_price=Decimal("160.00"))
        
        # (160 - 150) × 100 = $1,000
        assert pnl == Decimal("1000.00")
    
    def test_unrealized_pnl_loss(self) -> None:
        """Unrealized P&L when price decreases."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        pnl = position.unrealized_pnl(current_price=Decimal("140.00"))
        
        # (140 - 150) × 100 = -$1,000
        assert pnl == Decimal("-1000.00")
    
    def test_market_value(self) -> None:
        """Market value = quantity × current price."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        value = position.market_value(current_price=Decimal("160.00"))
        
        assert value == Decimal("16000.00")
    
    def test_cost_basis(self) -> None:
        """Cost basis = quantity × entry price."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        assert position.cost_basis == Decimal("15000.00")


class TestPositionModification:
    """Test adding and removing shares."""
    
    def test_add_shares_updates_average_price(self) -> None:
        """Adding shares recalculates weighted average entry price."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        # Add 100 more at $160
        position.add_shares(quantity=100, price=Decimal("160.00"))
        
        assert position.quantity == 200
        # Weighted avg: (100×150 + 100×160) / 200 = $155
        assert position.entry_price == Decimal("155.00")
    
    def test_remove_shares_returns_realized_pnl(self) -> None:
        """Removing shares returns realized P&L."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        # Sell 50 at $160
        realized_pnl = position.remove_shares(quantity=50, price=Decimal("160.00"))
        
        assert position.quantity == 50
        # (160 - 150) × 50 = $500
        assert realized_pnl == Decimal("500.00")
    
    def test_remove_shares_with_loss(self) -> None:
        """Realized P&L can be negative (loss)."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        realized_pnl = position.remove_shares(quantity=50, price=Decimal("140.00"))
        
        # (140 - 150) × 50 = -$500
        assert realized_pnl == Decimal("-500.00")
    
    def test_cannot_remove_more_than_held(self) -> None:
        """Can't sell more shares than you own."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        with pytest.raises(ValueError, match="Cannot remove"):
            position.remove_shares(quantity=150, price=Decimal("160.00"))
    
    def test_position_closed_when_all_removed(self) -> None:
        """Position is closed when quantity reaches zero."""
        position = Position("AAPL", 100, Decimal("150.00"))
        
        position.remove_shares(quantity=100, price=Decimal("160.00"))
        
        assert position.quantity == 0
        assert position.is_closed