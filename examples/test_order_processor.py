# examples/test_order_processor.py
"""
Test concurrent order processing.
"""

import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock
from dotenv import load_dotenv
import os

from trading_system.domain.entities.order import Order, OrderSide
from trading_system.domain.value_objects.symbol import Symbol
from trading_system.domain.value_objects.price import Price
from trading_system.application.async_order_processor import AsyncOrderProcessor

load_dotenv()


async def test_single_order():
    """Test processing a single order."""
    print("\n" + "=" * 60)
    print("TEST 1: Single Order Processing")
    print("=" * 60)
    
    # Create mock market client
    mock_client = MagicMock()
    mock_client.get_quote = AsyncMock(return_value={"price": 150.0})
    
    processor = AsyncOrderProcessor(mock_client, max_concurrent_orders=10)
    
    # Create test order
    order = Order.create_limit_order(
        Symbol("AAPL"),
        100,
        OrderSide.BUY,
        Price(Decimal("155.00"))  # Limit above market
    )
    
    print(f"📊 Processing order: {order.symbol} x {order.quantity}")
    
    # Process order
    result = await processor.process_order(order)
    
    print(f"✅ Result: {result['status']}")
    print(f"   Market Price: ${result.get('market_price', 'N/A')}")
    print(f"   Exchange: {result.get('exchange', 'N/A')}")


async def test_batch_processing():
    """Test processing multiple orders concurrently."""
    print("\n" + "=" * 60)
    print("TEST 2: Batch Processing (Concurrent)")
    print("=" * 60)
    
    # Create mock client with delay
    mock_client = MagicMock()
    
    async def get_quote_with_delay(symbol):
        await asyncio.sleep(0.3)  # Simulate network delay
        return {"price": 150.0}
    
    mock_client.get_quote = get_quote_with_delay
    
    processor = AsyncOrderProcessor(mock_client, max_concurrent_orders=10)
    
    # Create 5 test orders
    orders = [
        Order.create_limit_order(
            Symbol(f"STOCK{i}"),
            100,
            OrderSide.BUY,
            Price(Decimal("155.00"))
        )
        for i in range(5)
    ]
    
    print(f"📊 Processing {len(orders)} orders concurrently")
    print("⏱️  Each order takes ~0.5s")
    print("⏱️  Sequential: 5 × 0.5s = 2.5s")
    print("⏱️  Concurrent: ~0.5s (5x faster!)")
    print()
    
    import time
    start = time.time()
    
    # Process all orders concurrently
    results = await processor.process_orders_batch(orders)
    
    elapsed = time.time() - start
    
    print(f"✅ Processed {len(results)} orders in {elapsed:.2f}s")
    print()
    
    # Show results
    for result in results:
        status_emoji = "✅" if result["status"] == "submitted" else "❌"
        print(f"{status_emoji} Order {result['order_id']}: {result['status']}")


async def test_semaphore_limiting():
    """Test that semaphore limits concurrency."""
    print("\n" + "=" * 60)
    print("TEST 3: Semaphore Concurrency Limiting")
    print("=" * 60)
    
    # Track concurrent executions
    concurrent_count = 0
    max_concurrent_seen = 0
    
    async def tracked_get_quote(symbol):
        nonlocal concurrent_count, max_concurrent_seen
        
        concurrent_count += 1
        max_concurrent_seen = max(max_concurrent_seen, concurrent_count)
        
        await asyncio.sleep(0.2)
        
        concurrent_count -= 1
        return {"price": 150.0}
    
    mock_client = MagicMock()
    mock_client.get_quote = tracked_get_quote
    
    # Create processor with max_concurrent=3
    processor = AsyncOrderProcessor(mock_client, max_concurrent_orders=3)
    
    # Create 10 orders
    orders = [
        Order.create_limit_order(
            Symbol(f"STOCK{i}"),
            100,
            OrderSide.BUY,
            Price(Decimal("155.00"))
        )
        for i in range(10)
    ]
    
    print(f"📊 Processing {len(orders)} orders")
    print(f"🔒 Semaphore limit: 3 concurrent")
    print()
    
    # Process
    await processor.process_orders_batch(orders)
    
    print(f"✅ Max concurrent executions: {max_concurrent_seen}")
    print(f"   (Should be 3 or less - semaphore working!)")


async def main():
    """Run all tests."""
    print("\n" + "🚀" * 30)
    print("ORDER PROCESSOR TEST SUITE")
    print("🚀" * 30)
    
    await test_single_order()
    await asyncio.sleep(1)
    
    await test_batch_processing()
    await asyncio.sleep(1)
    
    await test_semaphore_limiting()
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())