""" Complete workflow testing """

from decimal import Decimal
import pytest

from trading_system.shared_kernel.exceptions import InsufficientFundsError
from trading_system.shared_kernel.value_objects.symbol import Symbol
from trading_system.contexts.portfolio_management.domain.entities.portfolio import Portfolio
from trading_system.contexts.order_management.domain.events import OrderCreatedEvent
from trading_system.contexts.portfolio_management.domain.entities.trade import Trade
from trading_system.shared_kernel.value_objects.money import Money

class TestTradingWorkflow:

    def test_complete_trading_session(self):
        """Test realistic trading sequence"""
        # Setup
        portfolio = Portfolio(name="Test", cash=Money(Decimal("100000")))
    
        # Execute trades
        trade1 = Trade.create_buy(Symbol("AAPL"), 100, Money(Decimal("150")))
        portfolio.execute_trade(trade1)
    
        assert portfolio.cash < Money(Decimal("100000"))    # Cash reduced
        assert portfolio.has_position(Symbol("AAPL"))
    
        # Partial sell
        trade2 = Trade.create_sell(Symbol("AAPL"), 50, Money(Decimal("160")))
        portfolio.execute_trade(trade2)
    
        assert portfolio.get_position(Symbol("AAPL")).quantity == 50
    
    def test_transaction_rollback(self):
        """ Test failed transaction rollback """
        portfolio = Portfolio(name="Test", cash=Money(Decimal("1000")))
        initial_cash = portfolio.cash

        with pytest.raises(InsufficientFundsError):
            with portfolio.transaction():
                # First succeeds 
                trade1 = Trade.create_buy(Symbol("AAPL"), 5, Money(Decimal("150")))
                print(f"Trade price: {trade1.price}")
                print(f"Trade quantity: {trade1.quantity}")
                print(f"Commission rate: {trade1.commission_rate}")
                print(f"Total value: {trade1.total_value}")
                portfolio.execute_trade(trade1)

                # Second fails - not enough money
                trade2 = Trade.create_buy(Symbol("MSFT"), 10, Money(Decimal("300")))
                portfolio.execute_trade(trade2)

        # Verify rollback
        assert portfolio.cash == initial_cash
        assert len(portfolio.positions) == 0
