"""
Unit tests for Order Simulator.
"""

from decimal import Decimal

import pytest

from paper_trading_service.domain.order_simulator import (
    OrderSimulator,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
)


class TestMarketOrders:
    """Test market order execution."""
    
    def test_buy_has_positive_slippage(self) -> None:
        """Buy orders cost more due to slippage."""
        simulator = OrderSimulator(slippage_bps=10)  # 10 bps = 0.1%
        
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        
        result = simulator.execute(request, market_price=Decimal("100.00"))
        
        assert result.filled
        # 10 bps on $100 = $0.10 slippage
        assert result.fill_price == Decimal("100.10")
        assert result.slippage == Decimal("0.10")
    
    def test_sell_has_negative_slippage(self) -> None:
        """Sell orders receive less due to slippage."""
        simulator = OrderSimulator(slippage_bps=10)
        
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        
        result = simulator.execute(request, market_price=Decimal("100.00"))
        
        assert result.filled
        assert result.fill_price == Decimal("99.90")
    
    def test_commission_calculated(self) -> None:
        """Commission included in result."""
        simulator = OrderSimulator(
            slippage_bps=0,
            commission_per_share=Decimal("0.01"),
            min_commission=Decimal("1.00"),
        )
        
        request = OrderRequest("AAPL", OrderSide.BUY, OrderType.MARKET, 100)
        result = simulator.execute(request, market_price=Decimal("100.00"))
        
        # 100 shares × $0.01 = $1.00
        assert result.commission == Decimal("1.00")
    
    def test_minimum_commission_enforced(self) -> None:
        """Small orders use minimum commission."""
        simulator = OrderSimulator(
            slippage_bps=0,
            commission_per_share=Decimal("0.005"),
            min_commission=Decimal("1.00"),
        )
        
        # 10 shares × $0.005 = $0.05 (below $1 minimum)
        request = OrderRequest("AAPL", OrderSide.BUY, OrderType.MARKET, 10)
        result = simulator.execute(request, market_price=Decimal("100.00"))
        
        assert result.commission == Decimal("1.00")


class TestLimitOrders:
    """Test limit order execution."""
    
    def test_buy_limit_fills_at_or_below_limit(self) -> None:
        """Buy limit fills when market ≤ limit price."""
        simulator = OrderSimulator(slippage_bps=0)
        
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=Decimal("100.00"),
        )
        
        # Market at $98 (below limit) → fills
        result = simulator.execute(request, market_price=Decimal("98.00"))
        
        assert result.filled
        assert result.fill_price == Decimal("98.00")
    
    def test_buy_limit_rejected_above_limit(self) -> None:
        """Buy limit rejected when market > limit price."""
        simulator = OrderSimulator(slippage_bps=0)
        
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=Decimal("100.00"),
        )
        
        # Market at $102 (above limit) → rejects
        result = simulator.execute(request, market_price=Decimal("102.00"))
        
        assert not result.filled
        assert result.rejection_reason is not None
    
    def test_sell_limit_fills_at_or_above_limit(self) -> None:
        """Sell limit fills when market ≥ limit price."""
        simulator = OrderSimulator(slippage_bps=0)
        
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=Decimal("100.00"),
        )
        
        # Market at $102 (above limit) → fills
        result = simulator.execute(request, market_price=Decimal("102.00"))
        
        assert result.filled
        assert result.fill_price == Decimal("102.00")
    
    def test_limit_order_requires_limit_price(self) -> None:
        """Limit orders must specify limit price."""
        with pytest.raises(ValueError, match="limit_price"):
            OrderRequest("AAPL", OrderSide.BUY, OrderType.LIMIT, 100)