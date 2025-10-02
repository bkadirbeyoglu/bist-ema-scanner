# examples/async_concepts.py
"""
Core async concepts with trading examples.
Demonstrates: coroutines, tasks, gather, await, event loop.
"""

import asyncio
from typing import List
import random


class AsyncConcepts:
    """Demonstrates async programming fundamentals."""
    
    async def coroutine_example(self, symbol: str) -> float:
        """
        COROUTINE: An async function that can pause and resume.
        
        Key Python features:
        - Defined with 'async def' (not just 'def')
        - Can use 'await' keyword inside
        - Returns a coroutine object when called
        - Must be 'awaited' or scheduled to run
        
        What happens when you call this:
        result = self.coroutine_example("AAPL")  # Creates coroutine object
        # Nothing runs yet! It's just a promise to run later
        
        result = await self.coroutine_example("AAPL")  # Actually runs
        # Now it executes and returns a value
        """
        print(f"📊 Fetching {symbol}...")
        
        # await asyncio.sleep() pauses THIS coroutine
        # During the pause, other coroutines can run
        # This is the magic of async - cooperative multitasking
        await asyncio.sleep(0.5)
        
        # Simulate random price
        price = random.uniform(100, 500)
        print(f"✅ {symbol}: ${price:.2f}")
        
        return price
    
    async def task_example(self, symbols: List[str]):
        """
        TASK: A coroutine scheduled for concurrent execution.
        
        asyncio.create_task() does two things:
        1. Wraps coroutine in a Task object
        2. Schedules it to run IMMEDIATELY in the event loop
        
        Without create_task:
        - Coroutines only run when awaited
        - They run sequentially
        
        With create_task:
        - Coroutines start running immediately in background
        - They run concurrently
        """
        print("\n" + "=" * 50)
        print("TASK EXAMPLE: Running tasks concurrently")
        print("=" * 50)
        
        tasks = []
        
        for symbol in symbols:
            # create_task() schedules the coroutine to run NOW
            # It doesn't wait - moves to next symbol immediately
            task = asyncio.create_task(self.coroutine_example(symbol))
            tasks.append(task)
        
        # At this point, all tasks are already running!
        # gather() just waits for them all to finish
        results = await asyncio.gather(*tasks)
        
        print(f"\n📈 Total portfolio value: ${sum(results):.2f}")
        return results
    
    async def gather_example(self, symbols: List[str]):
        """
        GATHER: Run multiple coroutines concurrently and collect results.
        
        asyncio.gather() is shorthand for:
        1. Create tasks for each coroutine
        2. Wait for all to complete
        3. Return list of results in order
        
        Key feature: return_exceptions=True
        - If one coroutine fails, others still run
        - Exceptions returned as values, not raised
        - Critical for resilient trading systems
        """
        print("\n" + "=" * 50)
        print("GATHER EXAMPLE: With error handling")
        print("=" * 50)
        
        # Simulate one symbol failing
        async def fetch_with_possible_error(symbol):
            if symbol == "FAIL":
                raise ValueError(f"Failed to fetch {symbol}")
            return await self.coroutine_example(symbol)
        
        # Add a failing symbol
        test_symbols = symbols + ["FAIL"]
        
        # return_exceptions=True means exceptions become results
        results = await asyncio.gather(
            *[fetch_with_possible_error(s) for s in test_symbols],
            return_exceptions=True  # Don't crash on errors!
        )
        
        # Check results
        print("\n📊 Results:")
        for symbol, result in zip(test_symbols, results):
            if isinstance(result, Exception):
                print(f"❌ {symbol}: {result}")
            else:
                print(f"✅ {symbol}: ${result:.2f}")
        
        return results
    
    async def await_example(self):
        """
        AWAIT: Pause current coroutine until another completes.
        
        'await' does three things:
        1. Pauses the current coroutine
        2. Returns control to event loop
        3. Resumes when awaited coroutine completes
        
        While paused, other coroutines can run!
        This is how async achieves concurrency.
        """
        print("\n" + "=" * 50)
        print("AWAIT EXAMPLE: Sequential async operations")
        print("=" * 50)
        
        print("⏸️  Before await - about to fetch AAPL")
        result = await self.coroutine_example("AAPL")
        print(f"▶️  After await - got result: ${result:.2f}")
        
        print("\n⏸️  Now fetching GOOGL")
        result2 = await self.coroutine_example("GOOGL")
        print(f"▶️  Got second result: ${result2:.2f}")
        
        return result + result2


async def demo():
    """
    Run all demonstrations.
    
    This function shows:
    - How to create and use async objects
    - Different patterns for concurrent execution
    - Error handling in async code
    """
    concepts = AsyncConcepts()
    
    symbols = ["AAPL", "GOOGL", "MSFT"]
    
    # Demo 1: Sequential awaits (slow)
    print("\n" + "🎯" * 20)
    print("Demo 1: Sequential Operations (Slow)")
    print("🎯" * 20)
    await concepts.await_example()
    
    # Demo 2: Concurrent tasks (fast)
    print("\n" + "🎯" * 20)
    print("Demo 2: Concurrent Tasks (Fast)")
    print("🎯" * 20)
    await concepts.task_example(symbols)
    
    # Demo 3: Error handling
    print("\n" + "🎯" * 20)
    print("Demo 3: Error Resilience")
    print("🎯" * 20)
    await concepts.gather_example(symbols)


if __name__ == "__main__":
    # asyncio.run() is the entry point for async programs
    # It does:
    # 1. Creates event loop
    # 2. Runs demo() coroutine
    # 3. Closes event loop when done
    asyncio.run(demo())