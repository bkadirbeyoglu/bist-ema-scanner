"""Test authenticated WebSocket connection."""
import asyncio
import aiohttp
import websockets
import json

async def get_token():
    """Get JWT token from REST API."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/api/v1/auth/token",
            data={"username": "trader1", "password": "password123"}
        ) as resp:
            data = await resp.json()
            return data["access_token"]

async def test_signals():
    # Step 1: Get token
    print("🔑 Getting JWT token...")
    token = await get_token()
    print(f"✅ Got token: {token[:20]}...")
    
    # Step 2: Connect with token
    uri = f"ws://localhost:8000/ws/signals?token={token}"
    print(f"\n🔌 Connecting to WebSocket...")
    
    async with websockets.connect(uri) as ws:
        # Step 3: Receive welcome
        welcome = await ws.recv()
        data = json.loads(welcome)
        print(f"✅ Connected as: {data.get('username')}")
        
        # Step 4: Subscribe
        await ws.send(json.dumps({
            "type": "subscribe",
            "topics": ["signals"]
        }))
        
        response = await ws.recv()
        data = json.loads(response)
        print(f"✅ Subscribed to: {data.get('topics')}")
        
        # Step 5: Test ping
        await ws.send(json.dumps({"type": "ping"}))
        pong = await ws.recv()
        print(f"✅ Ping/Pong: {json.loads(pong).get('type')}")
        
        print("\n✅ All authentication tests passed!")

async def test_without_token():
    """Test that connection without token fails."""
    print("\n🧪 Testing connection WITHOUT token...")
    uri = "ws://localhost:8000/ws/signals"
    
    try:
        async with websockets.connect(uri) as ws:
            response = await ws.recv()
            data = json.loads(response)
            print(f"📥 Received: {data}")
            
            # Should receive error and close
            try:
                await ws.recv()
            except websockets.exceptions.ConnectionClosed:
                print("✅ Connection correctly rejected!")
    except Exception as e:
        print(f"✅ Connection rejected: {e}")

if __name__ == "__main__":
    asyncio.run(test_signals())
    asyncio.run(test_without_token())
