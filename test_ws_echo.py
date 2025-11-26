"""Test WebSocket echo endpoint."""
import asyncio
import websockets
import json

async def test_echo():
    uri = "ws://localhost:8000/ws/echo"
    
    print("🔌 Connecting to WebSocket...")
    
    async with websockets.connect(uri) as ws:
        print("✅ Connected!")
        
        # Send test message
        test_msg = {"test": "Hello WebSocket!", "number": 42}
        await ws.send(json.dumps(test_msg))
        print(f"📤 Sent: {test_msg}")
        
        # Receive echo
        response = await ws.recv()
        data = json.loads(response)
        print(f"📥 Received: {data}")
        
        # Verify
        if data.get("data") == test_msg:
            print("✅ Echo test PASSED!")
        else:
            print("❌ Echo test FAILED!")

if __name__ == "__main__":
    asyncio.run(test_echo())
