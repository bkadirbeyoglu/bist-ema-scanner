# examples/test_market_client.py
"""
Test the market data client with real API calls.
Run this after implementing the client.
"""

import asyncio
from decimal import Decimal
from dotenv import load_dotenv
import os

from trading_system.infrastructure.market_data.alpha_vantage import AlphaVantageClient
from trading_system.domain.value_objects.symbol import Symbol

# Load environment variables
load_dotenv()


async def test_single_quote():
    """Test fetching a single stock quote."""
    print("\n" + "=" * 60)
    print("TEST 1: Single Quote")
    print("=" * 60)
    
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    
    if not api_key:
        print("❌ Error: ALPHA_VANTAGE_API_KEY not found in .env")
        return False
    
    # Use async context manager (automatically closes session)
    async with AlphaVantageClient(api_key) as client:
        print("📊 Fetching AAPL quote...")
        
        try:
            # Get quote as dictionary
            quote = await client.get_quote("AAPL")
            print(f"✅ Success!")
            print(f"   Symbol: {quote['symbol']}")
            print(f"   Price: ${quote['price']:.2f}")
            print(f"   Volume: {quote['volume']:,}")
            print(f"   Change: {quote['change_percent']}")
            
            # Get quote as Price object (domain model)
            price_obj = await client.get_price_object("AAPL")
            print(f"   Price Object: {price_obj}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_multiple_quotes():
    """Test fetching multiple quotes concurrently."""
    print("\n" + "=" * 60)
    print("TEST 2: Multiple Quotes (Concurrent)")
    print("=" * 60)
    
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    
    async with AlphaVantageClient(api_key) as client:
        symbols = ["AAPL", "GOOGL", "MSFT"]
        print(f"📊 Fetching quotes for: {', '.join(symbols)}")
        print("⏱️  This respects rate limiting (5/minute on free tier)")
        print()
        
        try:
            import time
            start = time.time()
            
            # Fetch all quotes concurrently
            quotes = await client.get_quotes(symbols)
            
            elapsed = time.time() - start
            
            print(f"✅ Fetched {len(symbols)} quotes in {elapsed:.2f} seconds")
            print()
            
            for symbol, quote in quotes.items():
                if quote:
                    print(f"✅ {symbol:6} ${quote['price']:8.2f}  {quote['change_percent']:>8}")
                else:
                    print(f"❌ {symbol:6} Failed to fetch")
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_rate_limiting():
    """Test that rate limiting works correctly."""
    print("\n" + "=" * 60)
    print("TEST 3: Rate Limiting")
    print("=" * 60)
    
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    
    async with AlphaVantageClient(api_key) as client:
        print("📊 Making 7 requests (rate limit is 5/minute)")
        print("⏱️  First 5 should go immediately")
        print("⏱️  Requests 6-7 should wait for rate limiter")
        print()
        
        import time
        
        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA", "AMD", "INTC"]
        
        for i, symbol in enumerate(symbols, 1):
            start = time.time()
            
            try:
                await client.get_quote(symbol)
                elapsed = time.time() - start
                print(f"✅ Request {i}/7: {symbol:6} fetched in {elapsed:.2f}s")
                
            except Exception as e:
                print(f"❌ Request {i}/7: {symbol:6} failed: {e}")
        
        return True


async def main():
    """Run all tests."""
    print("\n" + "🚀" * 30)
    print("MARKET DATA CLIENT TEST SUITE")
    print("🚀" * 30)
    
    # Test 1: Single quote
    success1 = await test_single_quote()
    
    # Test 2: Multiple quotes
    if success1:
        await asyncio.sleep(2)  # Brief pause between tests
        success2 = await test_multiple_quotes()
    
    # Test 3: Rate limiting (optional - takes time)
    # Uncomment to test:
    # if success1 and success2:
    #     await asyncio.sleep(2)
    #     await test_rate_limiting()
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    print()
    print("💡 Next steps:")
    print("   1. Try fetching different stock symbols")
    print("   2. Integrate with domain model (Portfolio valuation)")
    print("   3. Add caching to reduce API calls")


if __name__ == "__main__":
    asyncio.run(main())