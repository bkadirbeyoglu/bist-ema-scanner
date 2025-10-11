"""
End-to-end integration test.

TESTING PHILOSOPHY:
===================

Integration tests verify:
1. Components work together correctly
2. Data flows through entire system
3. State changes are consistent
4. Errors are handled gracefully

Unlike unit tests (mock everything), integration tests use:
- Real components (Event Bus, Portfolio, Strategy)
- Real data flow (events published and consumed)
- Real state changes (portfolio balance updates)

This catches bugs that unit tests miss:
- Type mismatches between components
- Timing/ordering issues
- State synchronization problems
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from typing import ClassVar
import uuid

from trading_system.shared_kernel.event_bus import InMemoryEventBus
from trading_system.shared_kernel.events import BaseEvent
from trading_system.shared_kernel.logging_config import setup_logging, log_context, get_logger
from trading_system.order_management.domain.events import OrderCreatedEvent, OrderType, OrderSide
from trading_system.domain.entities.portfolio import Portfolio
from trading_system.domain.entities.trade import Trade, TradeType
from trading_system.domain.value_objects.money import Money
from trading_system.domain.value_objects.symbol import Symbol
from trading_system.domain.value_objects.price import Price

logger = get_logger(__name__)


# ============================================================================
# DOMAIN EVENTS FOR TESTING
# ============================================================================
# These events are defined here for the integration test.
# In a real system, they would be in their respective bounded contexts.

@dataclass(frozen=True)
class PriceUpdatedEvent(BaseEvent):
    """
    Event for price updates from market data.
    
    This event is published by:
    - WebSocket client (real-time)
    - Market data poller (backup)
    - Test fixtures (testing)
    
    Consumed by:
    - Trading strategies
    - Risk management
    - UI updates
    """
    symbol: str
    price: Decimal
    volume: int = 0


# ============================================================================
# SIMPLE TRADING STRATEGY
# ============================================================================

class SimpleMeanReversionStrategy:
    """
    Simple mean-reversion trading strategy for testing.
    
    STRATEGY LOGIC:
    - Track reference price per symbol
    - If price drops 2%+ → BUY signal (expecting reversion)
    - If price rises 2%+ → SELL signal (taking profit)
    
    This demonstrates:
    - Event subscription (listening to PriceUpdatedEvent)
    - Event publication (generating OrderCreatedEvent)
    - State management (reference_prices dictionary)
    - Business logic (percentage change calculation)
    """
    
    def __init__(self, event_bus: InMemoryEventBus, portfolio: Portfolio):
        """
        Initialize strategy with event bus and portfolio.
        
        Parameters:
        -----------
        event_bus: InMemoryEventBus
            For subscribing to events and publishing signals
        
        portfolio: Portfolio
            For checking current positions and cash
        """
        self.event_bus = event_bus
        self.portfolio = portfolio
        self.reference_prices = {}  # {symbol: Decimal}
        
        # Subscribe to price updates
        # When PriceUpdatedEvent published → on_price_update() called
        event_bus.subscribe(PriceUpdatedEvent, self.on_price_update)
        
        logger.info("Strategy initialized", extra={
            "initial_cash": str(portfolio.cash.amount)
        })
    
    async def on_price_update(self, event: PriceUpdatedEvent):
        """
        Handle price updates and generate trading signals.
        
        FLOW:
        1. Get current price from event
        2. Compare to reference price
        3. Calculate percentage change
        4. If change > threshold → generate signal
        5. Publish OrderCreatedEvent
        
        WHY ASYNC?
        - Might need to fetch additional data (await)
        - Publishes events (await event_bus.publish)
        - Non-blocking (other handlers run concurrently)
        """
        symbol = event.symbol
        current_price = event.price
        
        logger.debug("Price update received", extra={
            "symbol": symbol,
            "price": str(current_price)
        })
        
        # First time seeing this symbol → set reference
        if symbol not in self.reference_prices:
            self.reference_prices[symbol] = current_price
            logger.info("Reference price set", extra={
                "symbol": symbol,
                "price": str(current_price)
            })
            return  # No signal on first price
        
        # Calculate change from reference
        ref_price = self.reference_prices[symbol]
        change_pct = ((current_price - ref_price) / ref_price) * 100
        
        logger.debug("Price change calculated", extra={
            "symbol": symbol,
            "reference": str(ref_price),
            "current": str(current_price),
            "change_pct": f"{change_pct:.2f}%"
        })
        
        # Generate signal if threshold met
        if change_pct <= -2.0:  # Dropped 2%+ → BUY
            logger.info("BUY signal generated", extra={
                "symbol": symbol,
                "change_pct": f"{change_pct:.2f}%"
            })
            await self._generate_buy_signal(symbol, current_price)
            # Update reference after signal
            self.reference_prices[symbol] = current_price
        
        elif change_pct >= 2.0:  # Rose 2%+ → SELL
            logger.info("SELL signal generated", extra={
                "symbol": symbol,
                "change_pct": f"{change_pct:.2f}%"
            })
            await self._generate_sell_signal(symbol, current_price)
            # Update reference after signal
            self.reference_prices[symbol] = current_price
    
    async def _generate_buy_signal(self, symbol: str, price: Decimal):
        """
        Generate buy order event.
        
        BUSINESS LOGIC:
        - Calculate position size based on available cash
        - Maximum 10% of portfolio per position
        - Minimum 1 share
        """
        # Calculate how much we can buy
        max_investment = self.portfolio.cash.amount * Decimal("0.10")  # 10% of cash
        quantity = int(max_investment / price)
        
        if quantity < 1:
            logger.warning("Insufficient funds for trade", extra={
                "symbol": symbol,
                "cash": str(self.portfolio.cash.amount),
                "price": str(price)
            })
            return
        
        # Create order event
        order_event = OrderCreatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            order_id=f"ORDER-{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            quantity=Decimal(str(quantity)),
            price=price,
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            account_id="TEST-ACCOUNT",
            metadata={"strategy": "mean_reversion", "signal": "buy"}
        )
        
        # Publish order event
        await self.event_bus.publish(order_event)
        
        logger.info("Buy order published", extra={
            "order_id": order_event.order_id,
            "symbol": symbol,
            "quantity": quantity,
            "price": str(price)
        })
    
    async def _generate_sell_signal(self, symbol: str, price: Decimal):
        """Generate sell order event (if we have position)."""
        position = self.portfolio.get_position(Symbol(symbol))
        
        if not position or position.quantity <= 0:
            logger.warning("No position to sell", extra={"symbol": symbol})
            return
        
        # Create order event
        order_event = OrderCreatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            order_id=f"ORDER-{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            quantity=Decimal(str(position.quantity)),
            price=price,
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            account_id="TEST-ACCOUNT",
            metadata={"strategy": "mean_reversion", "signal": "sell"}
        )
        
        # Publish order event
        await self.event_bus.publish(order_event)
        
        logger.info("Sell order published", extra={
            "order_id": order_event.order_id,
            "symbol": symbol,
            "quantity": position.quantity,
            "price": str(price)
        })


# ============================================================================
# ORDER EXECUTION HANDLER
# ============================================================================

class OrderExecutionHandler:
    """
    Handles order execution by updating portfolio.
    
    In real system, this would:
    - Send orders to broker API
    - Wait for fill confirmations
    - Handle partial fills
    - Manage order lifecycle
    
    For testing, we:
    - Execute orders immediately
    - Update portfolio directly
    - Simulate successful execution
    """
    
    def __init__(self, event_bus: InMemoryEventBus, portfolio: Portfolio):
        self.event_bus = event_bus
        self.portfolio = portfolio
        
        # Subscribe to order events
        event_bus.subscribe(OrderCreatedEvent, self.on_order_created)
        
        logger.info("Order execution handler initialized")
    
    async def on_order_created(self, event: OrderCreatedEvent):
        """
        Execute order when OrderCreatedEvent received.
        
        Simulates immediate execution (for testing).
        """
        logger.info("Executing order", extra={
            "order_id": event.order_id,
            "symbol": event.symbol,
            "side": event.side.value,
            "quantity": str(event.quantity)
        })
        
        try:
            # IMPORTANT: Trade expects Money (with currency), not Price
            # Money has both amount and currency attributes
            # Price only has value attribute
            trade_price = Money(event.price, "USD")  # Convert to Money with currency
            
            # Create trade from order
            trade = Trade.create_buy(
                Symbol(event.symbol),
                int(event.quantity),
                trade_price  # Now passing Money, not Price
            ) if event.side == OrderSide.BUY else Trade.create_sell(
                Symbol(event.symbol),
                int(event.quantity),
                trade_price  # Now passing Money, not Price
            )
            
            # Execute trade on portfolio
            self.portfolio.execute_trade(trade)
            
            logger.info("Order executed successfully", extra={
                "order_id": event.order_id,
                "trade_id": str(trade.id),
                "portfolio_cash": str(self.portfolio.cash.amount)
            })
            
        except Exception as e:
            logger.error("Order execution failed", extra={
                "order_id": event.order_id,
                "error": str(e)
            }, exc_info=True)
            # Re-raise so test can see the failure
            raise


# ============================================================================
# INTEGRATION TEST
# ============================================================================

@pytest.mark.asyncio
async def test_complete_trading_cycle():
    """
    Test complete workflow: Price → Signal → Order → Execution.
    
    TEST SCENARIO:
    1. Initialize system (event bus, portfolio, strategy, order handler)
    2. Publish initial price (sets reference)
    3. Publish lower price (triggers buy signal)
    4. Verify order created and executed
    5. Check portfolio state (position created, cash reduced)
    
    WHAT WE'RE VERIFYING:
    - Events flow through system correctly
    - Strategy logic triggers on conditions
    - Orders are generated properly
    - Portfolio updates consistently
    - No errors or exceptions
    - Correlation IDs trace through workflow
    """
    
    # Setup structured logging to see flow
    setup_logging(level="INFO", json_format=False)
    
    # Use correlation ID to trace this test
    with log_context(test_name="complete_cycle"):
        
        logger.info("=" * 60)
        logger.info("Starting Complete Trading Cycle Test")
        logger.info("=" * 60)
        
        # ARRANGE: Set up components
        event_bus = InMemoryEventBus()
        
        portfolio = Portfolio(
            name="Test Portfolio", 
            cash=Money(Decimal("100000"))  # $100k starting cash
        )
        
        strategy = SimpleMeanReversionStrategy(event_bus, portfolio)
        order_handler = OrderExecutionHandler(event_bus, portfolio)
        
        logger.info("System initialized", extra={
            "initial_cash": str(portfolio.cash.amount),
            "initial_positions": len(portfolio.positions)
        })
        
        # Give time for subscriptions to register
        await asyncio.sleep(0.1)
        
        # ACT 1: Publish initial price
        # This sets the reference price in strategy
        logger.info("Publishing initial price...")
        initial_event = PriceUpdatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            symbol="AAPL",
            price=Decimal("150.00"),  # Reference: $150
            volume=1000
        )
        await event_bus.publish(initial_event)
        await asyncio.sleep(0.2)  # Let event process
        
        # ACT 2: Publish lower price (trigger buy)
        # -2.5% change should trigger buy signal
        logger.info("Publishing price drop (trigger buy signal)...")
        drop_event = PriceUpdatedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            version=1,
            symbol="AAPL",
            price=Decimal("146.25"),  # $150 - 2.5% = $146.25
            volume=1500
        )
        await event_bus.publish(drop_event)
        await asyncio.sleep(0.3)  # Let order execute
        
        # ASSERT: Verify expected state
        logger.info("Verifying results...")
        
        # Portfolio should have AAPL position
        assert portfolio.has_position(Symbol("AAPL")), \
            "Portfolio should have AAPL position after buy signal"
        
        # At least one trade should be recorded
        assert len(portfolio.trades) >= 1, \
            f"Portfolio should have executed at least one trade, got {len(portfolio.trades)}"
        
        # Verify cash was reduced (trade executed)
        assert portfolio.cash.amount < Decimal("100000"), \
            f"Portfolio cash should be reduced after buying shares, got {portfolio.cash.amount}"
        
        # Log final state