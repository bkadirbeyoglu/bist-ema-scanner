"""Test market data streaming."""
import asyncio
import aiohttp
import websockets
import json

async def get_token():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/api/v1/auth/token",
            data={"username": "trader1", "password": "password123"}
        ) as resp:
            return (await resp.json())["access_token"]

async def watch_prices(symbol: str, count: int = 5):
    token = await get_token()
    uri = f"ws://localhost:8000/ws/market-data/{symbol}?token={token}"
    
    print(f"📈 Connecting to {symbol} market data...")
    
    async with websockets.connect(uri) as ws:
        # Welcome
        welcome = await ws.recv()
        print(f"✅ {json.loads(welcome).get('message')}")
        
        # Receive price updates
        for i in range(count):
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get("type") == "market_data":
                print(f"   {data['symbol']}: ${data['price']} "
                      f"(bid: {data['bid']}, ask: {data['ask']})")
        
        print(f"\n✅ Received {count} price updates!")

if __name__ == "__main__":
    asyncio.run(watch_prices("AAPL", 5))
