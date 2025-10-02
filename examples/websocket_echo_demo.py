# examples/websocket_echo_demo.py
"""
WebSocket echo server test - simplest possible example.
"""

import asyncio
import websockets
import json
from datetime import datetime


async def test_echo_server():
    """
    Test with public echo server.
    
    Echo server just sends back whatever you send it.
    Good for testing WebSocket basics without API keys.
    """
    print("\n" + "=" * 60)
    print("WebSocket Echo Server Demo")
    print("=" * 60)
    
    url = "wss://echo.websocket.org"
    
    print(f"📡 Connecting to {url}")
    
    try:
        # Connect to WebSocket
        async with websockets.connect(url) as ws:
            print("✅ Connected!")
            
            # Send a message
            message = {
                "type": "test",
                "symbol": "AAPL",
                "timestamp": datetime.now().isoformat()
            }
            
            print(f"\n📤 Sending: {message}")
            await ws.send(json.dumps(message))
            
            # Receive echo
            response = await ws.recv()
            print(f"📥 Received: {response}")
            
            print("\n✅ Echo test successful!")
            
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_echo_server())