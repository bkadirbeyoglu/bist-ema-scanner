# src/trading_system/application/async_order_processor.py
"""
Async order processor for concurrent order handling.

This demonstrates:
- Semaphore pattern for concurrency control
- Async workflow orchestration
- Error isolation (one failure doesn't stop others)
- Integration with domain model
"""

import asyncio
from typing import List, Dict, Optional, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from enum import Enum

from trading_system.domain.entities.order import Order, OrderStatus, OrderSide
from trading_system.domain.value_objects.symbol import Symbol
from trading_system.domain.value_objects.price import Price
from trading_system.infrastructure.market_data.base_client import AsyncMarketDataClient


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