import asyncio
from typing import List, Dict, Optional, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from enum import Enum

from trading_system.contexts.order_management.domain.entities.order import Order
from trading_system.shared_kernel.value_objects import symbol
from trading_system.shared_kernel.value_objects.price import Price
from trading_system.shared_kernel.value_objects.symbol import Symbol
from trading_system.contexts.order_management.domain.entities.order import OrderStatus
from trading_system.contexts.market_data.infrastructure.base_client import AsyncMarketDataClient


class OrderProcessingStatus(Enum):
    """Processing states for monitoring."""
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    ROUTING = "ROUTING"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"


class AsyncOrderProcessor:
    """
    Process orders asynchronously with concurrency control.
    
    THE SEMAPHORE PATTERN:
    ====================
    A semaphore is like a bouncer at a club: "Only N people inside at once"
    
    Why limit concurrency?
    - API rate limits
    - Memory constraints
    - Connection limits
    - Fair resource sharing
    
    Example with max_concurrent=2:
    - Orders 1 & 2: Start immediately
    - Order 3: Waits
    - Order 1 completes: Order 3 can start
    """
    
    def __init__(
        self,
        market_client: AsyncMarketDataClient,
        max_concurrent_orders: int = 10
    ):
        """
        Initialize processor.
        
        Parameters:
        -----------
        market_client: AsyncMarketDataClient
            For fetching current prices
        
        max_concurrent_orders: int
            Maximum parallel orders
            - Too low (1-5): Underutilizes resources
            - Too high (100+): Overwhelms APIs
            - Sweet spot (10-50): Balance performance/resources
        """
        self.market_client = market_client
        self.max_concurrent = max_concurrent_orders
        
        # Semaphore limits concurrent processing
        self._semaphore = asyncio.Semaphore(max_concurrent_orders)
        
        # Track processing status
        self._processing: Dict[UUID, OrderProcessingStatus] = {}
    
    async def process_order(self, order: Order) -> Dict[str, Any]:
        """
        Process a single order asynchronously.
        
        Workflow:
        1. VALIDATE: Check order parameters
        2. FETCH PRICE: Get current market price
        3. CHECK CONDITIONS: Can we execute?
        4. SUBMIT: Send to exchange
        5. UPDATE: Mark order as submitted
        """
        # Enter semaphore - wait if max concurrent reached
        async with self._semaphore:
            order_id = order.id
            
            try:
                # STEP 1: VALIDATE
                self._processing[order_id] = OrderProcessingStatus.VALIDATING
                
                if not await self._validate_order(order):
                    return {
                        "status": "failed",
                        "order_id": order_id,
                        "reason": "validation failed"
                    }
                
                # STEP 2: FETCH CURRENT MARKET PRICE
                self._processing[order_id] = OrderProcessingStatus.ROUTING
                current_price = await self._get_market_price(order.symbol)
                
                # STEP 3: CHECK EXECUTION CONDITIONS
                if await self._check_execution(order, current_price):
                    # STEP 4: SUBMIT TO EXCHANGE
                    self._processing[order_id] = OrderProcessingStatus.SUBMITTED
                    result = await self._submit_to_exchange(order)
                    
                    # STEP 5: UPDATE DOMAIN MODEL
                    order.submit()
                    
                    return {
                        "status": "submitted",
                        "order_id": order_id,
                        "market_price": float(current_price.value),
                        **result
                    }
                
                return {
                    "status": "failed",
                    "order_id": order_id,
                    "reason": "conditions not met"
                }
                
            except Exception as e:
                # Error isolation: one failure doesn't stop others
                return {
                    "status": "failed",
                    "order_id": order_id,
                    "reason": str(e)
                }
                
            finally:
                # Cleanup
                if order_id in self._processing:
                    del self._processing[order_id]
    
    async def process_orders_batch(
        self,
        orders: List[Order]
    ) -> List[Dict[str, Any]]:
        """
        Process multiple orders concurrently.
        
        With 20 orders, max_concurrent=10:
        
        Time 0.0s: Orders 1-10 start
        Time 0.5s: Orders 3,7 complete → 11,12 start
        Time 1.0s: Remaining complete → 13-20 start
        Time 1.5s: All done
        
        Sequential: 20 × 500ms = 10 seconds
        Concurrent: ~1.5 seconds (6-7x faster!)
        """
        # Create tasks for all orders
        tasks = [self.process_order(order) for order in orders]
        
        # Run concurrently, isolate failures
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        processed = []
        for order, result in zip(orders, results):
            if isinstance(result, Exception):
                processed.append({
                    "status": "error",
                    "order_id": order.id,
                    "error": str(result)
                })
            else:
                processed.append(result)
        
        return processed
    
    async def _validate_order(self, order: Order) -> bool:
        """Validate order asynchronously."""
        # Simulate validation (would be DB query or API call)
        await asyncio.sleep(0.1)
        
        # Basic validation
        return order.quantity > 0 and order.status == OrderStatus.PENDING
    
    async def _get_market_price(self, symbol: Symbol) -> Price:
        """Get current market price."""
        # Use market client (async API call)
        quote = await self.market_client.get_quote(str(symbol))
        
        if quote and "price" in quote:
            return Price(Decimal(str(quote["price"])))
        
        # Fallback for demo
        return Price(Decimal("100.00"))
    
    async def _check_execution(self, order: Order, market_price: Price) -> bool:
        """Check if order can execute at current market conditions."""
        if order.limit_price:
            if order.side.value == "BUY":
                # Buy: only if market price at or below limit
                return market_price.value <= order.limit_price.value
            else:  # SELL
                # Sell: only if market price at or above limit
                return market_price.value >= order.limit_price.value
        
        # Market orders always execute
        return True
    
    async def _submit_to_exchange(self, order: Order) -> Dict[str, Any]:
        """Submit order to exchange (simulated)."""
        # Simulate network delay
        await asyncio.sleep(0.2)
        
        # Return simulated exchange response
        return {
            "exchange": "NASDAQ",
            "exchange_order_id": f"EX{order.id.hex[:8]}"
        }
    

"""
Application services for Order Management context.

This file contains:
- OrderProcessingStatus (Enum) - from Day 2
- AsyncOrderProcessor - from Day 2
- OrderManagementService - NEW in Part 3 (add below)
"""

import logging
from uuid import UUID
from typing import Optional, List
from decimal import Decimal

from trading_system.shared_kernel.event_bus import InMemoryEventBus
from trading_system.contexts.order_management.domain.entities.order import (
    Order, OrderSide, OrderType
)
from trading_system.contexts.order_management.domain.repositories import (
    OrderRepository
)
from trading_system.contexts.order_management.domain.events import (
    OrderCreatedEvent
)
from trading_system.shared_kernel.value_objects.symbol import Symbol
from trading_system.shared_kernel.value_objects.price import Price


logger = logging.getLogger(__name__)

# ADD this new class to the existing services.py file
class OrderManagementService:
    """
    Application service for order management.
    
    DEPENDENCY INJECTION:
    - order_repository: Where to store orders
    - event_bus: How to publish events
    """
    def __init__(self, order_repository: OrderRepository, event_bus: InMemoryEventBus):
        self.order_repository = order_repository
        self.event_bus = event_bus

    async def create_order(
        self,
        symbol: str,
        quantity: Decimal,
        side: OrderSide,
        order_type: OrderType,
        limit_price: Optional[Decimal] = None
    ) -> Order:
        """Create a new order."""
        logger.info(f"Creating order: {symbol} {side.value} {quantity}")
        
        # Step 1: Create domain object
        symbol_obj = Symbol(symbol)
        
        if order_type == OrderType.LIMIT:
            if not limit_price:
                raise ValueError("Limit orders require limit_price")
            price_obj = Price(limit_price)
            order = Order.create_limit_order(
                symbol=symbol_obj,
                quantity=int(quantity),
                side=side,
                limit_price=price_obj
            )
        else:
            order = Order.create_market_order(
                symbol=symbol_obj,
                quantity=int(quantity),
                side=side
            )
        
        # Step 2: Save via repository
        await self.order_repository.save(order)
        logger.info(f"Order saved: {order.id}")
        
        # Step 3: Publish domain event
        event = OrderCreatedEvent(
            event_id=str(order.id),
            timestamp=order.created_at,
            version=1,
            order_id=str(order.id),
            symbol=str(order.symbol),
            quantity=Decimal(str(order.quantity)),
            price=limit_price or Decimal("0"),
            order_type=order_type,
            side=side,
            account_id=None,
            metadata={}
        )
        
        await self.event_bus.publish(event)
        logger.info(f"OrderCreatedEvent published for {order.id}")
        
        return order
    
    async def get_order(self, order_id: UUID) -> Optional[Order]:
        """Retrieve order by ID."""
        return await self.order_repository.find_by_id(order_id)
    
    async def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        """Get all orders for a symbol."""
        return await self.order_repository.find_by_symbol(symbol)
    
    async def get_active_orders(self) -> List[Order]:
        """Get all active orders."""
        return await self.order_repository.find_active_orders()