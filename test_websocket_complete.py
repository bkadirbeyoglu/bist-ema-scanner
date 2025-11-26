"""Complete WebSocket test suite."""
import asyncio
import aiohttp
import websockets
import json

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"


async def get_token(username="trader1", password="password123"):
    """Get JWT token."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/api/v1/auth/token",
            data={"username": username, "password": password}
        ) as resp:
            return (await resp.json())["access_token"]


async def test_echo():
    """Test echo endpoint (no auth)."""
    print("\n1️⃣ Testing /ws/echo (no auth)...")
    
    async with websockets.connect(f"{WS_URL}/ws/echo") as ws:
        await ws.send(json.dumps({"test": "hello"}))
        response = json.loads(await ws.recv())
        
        assert response["type"] == "echo"
        assert response["data"]["test"] == "hello"
        print("   ✅ Echo works!")


async def test_auth_required():
    """Test that auth is required for signals."""
    print("\n2️⃣ Testing auth requirement...")
    
    async with websockets.connect(f"{WS_URL}/ws/signals") as ws:
        # Connection accepts, then receives error and closes
        response = json.loads(await ws.recv())
        assert response["type"] == "error"
        assert response["code"] == 4001
        assert "token" in response["message"].lower()
        print("   ✅ Auth correctly required!")


async def test_authenticated_signals():
    """Test authenticated signals endpoint."""
    print("\n3️⃣ Testing authenticated /ws/signals...")
    
    token = await get_token()
    uri = f"{WS_URL}/ws/signals?token={token}"
    
    async with websockets.connect(uri) as ws:
        # Welcome
        welcome = json.loads(await ws.recv())
        assert welcome["type"] == "connected"
        assert "username" in welcome
        print(f"   ✅ Connected as: {welcome['username']}")
        
        # Subscribe
        await ws.send(json.dumps({
            "type": "subscribe",
            "topics": ["signals"]
        }))
        response = json.loads(await ws.recv())
        assert response["type"] == "subscribed"
        print(f"   ✅ Subscribed to: {response['topics']}")


async def test_market_data():
    """Test market data streaming."""
    print("\n4️⃣ Testing /ws/market-data/AAPL...")
    
    token = await get_token()
    uri = f"{WS_URL}/ws/market-data/AAPL?token={token}"
    
    async with websockets.connect(uri) as ws:
        # Welcome
        welcome = json.loads(await ws.recv())
        assert "AAPL" in welcome.get("message", "")
        
        # Get one price update
        update = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
        assert update["type"] == "market_data"
        assert update["symbol"] == "AAPL"
        assert "price" in update
        print(f"   ✅ Received: AAPL @ ${update['price']}")


async def test_signal_broadcast():
    """Test signal broadcasting."""
    print("\n5️⃣ Testing signal broadcast...")
    
    token = await get_token()
    uri = f"{WS_URL}/ws/signals?token={token}"
    
    async with websockets.connect(uri) as ws:
        await ws.recv()  # welcome
        await ws.send(json.dumps({"type": "subscribe", "topics": ["signals"]}))
        await ws.recv()  # subscribed
        
        # Publish signal via HTTP
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}/ws/test/publish-signal",
                params={"symbol": "TEST", "signal_type": "BUY", "price": 100}
            ) as resp:
                result = await resp.json()
                print(f"   Published to {result['clients_notified']} clients")
        
        # Receive signal
        signal = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert signal["type"] == "signal"
        assert signal["symbol"] == "TEST"
        print(f"   ✅ Received signal: {signal['signal_type']} {signal['symbol']}")


async def test_stats():
    """Test stats endpoint."""
    print("\n6️⃣ Testing /ws/stats...")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/ws/stats") as resp:
            stats = await resp.json()
            print(f"   ✅ Connections: {stats['total_connections']}")
            print(f"   ✅ Topics: {stats['total_topics']}")


async def main():
    print("=" * 50)
    print("WebSocket Complete Test Suite")
    print("=" * 50)
    
    try:
        await test_echo()
        await test_auth_required()
        await test_authenticated_signals()
        await test_market_data()
        await test_signal_broadcast()
        await test_stats()
        
        print("\n" + "=" * 50)
        print("✅ ALL TESTS PASSED!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
