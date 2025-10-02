# examples/sync_vs_async_demo.py
"""
Demonstrating the difference between sync and async execution.
This will be crucial for our event handlers from Session 1.
"""

import time
import asyncio
from datetime import datetime


# SYNCHRONOUS VERSION - Blocking
def fetch_price_sync(symbol: str) -> float:
    """Simulate fetching price from API (blocking)."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching {symbol}...")
    time.sleep(1)  # Simulates network delay - BLOCKS entire program!
    price = {"AAPL": 150.0, "GOOGL": 2800.0, "MSFT": 380.0}.get(symbol, 100.0)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {symbol} = ${price}")
    return price


def get_portfolio_value_sync(symbols: list) -> float:
    """Get portfolio value synchronously - SLOW!"""
    total = 0
    for symbol in symbols:
        price = fetch_price_sync(symbol)  # Each call blocks for 1 second
        total += price
    return total


# ASYNCHRONOUS VERSION - Non-blocking
async def fetch_price_async(symbol: str) -> float:
    """Simulate fetching price from API (non-blocking)."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching {symbol}...")
    await asyncio.sleep(1)  # Simulates network delay - DOESN'T block!
    price = {"AAPL": 150.0, "GOOGL": 2800.0, "MSFT": 380.0}.get(symbol, 100.0)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {symbol} = ${price}")
    return price


async def get_portfolio_value_async(symbols: list) -> float:
    """Get portfolio value asynchronously - FAST!"""
    # Create tasks for all symbols - they run CONCURRENTLY
    tasks = [fetch_price_async(symbol) for symbol in symbols]
    prices = await asyncio.gather(*tasks)  # Wait for all to complete
    return sum(prices)


def main():
    """Compare sync vs async performance."""
    symbols = ["AAPL", "GOOGL", "MSFT"]
    
    print("=" * 50)
    print("SYNCHRONOUS EXECUTION (Sequential)")
    print("=" * 50)
    start = time.time()
    total_sync = get_portfolio_value_sync(symbols)
    sync_time = time.time() - start
    print(f"Total: ${total_sync:.2f}")
    print(f"Time: {sync_time:.2f} seconds\n")
    
    print("=" * 50)
    print("ASYNCHRONOUS EXECUTION (Concurrent)")
    print("=" * 50)
    start = time.time()
    total_async = asyncio.run(get_portfolio_value_async(symbols))
    async_time = time.time() - start
    print(f"Total: ${total_async:.2f}")
    print(f"Time: {async_time:.2f} seconds\n")
    
    print(f"🚀 Speedup: {sync_time/async_time:.1f}x faster with async!")


if __name__ == "__main__":
    main()