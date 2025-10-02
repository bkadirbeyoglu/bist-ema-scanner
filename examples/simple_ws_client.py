# examples/simple_ws_client.py
"""
Simple WebSocket client to connect to our market data server.
"""

import asyncio
import websockets
import json


async def receive_market_data():
    """
    Connect to WebSocket server and receive market data.
    """
    print("\n" + "=" * 60)
    print("WebSocket Market Data Client")
    print("=" * 60)
    
    url = "ws://localhost:8765"
    print(f"📡 Connecting to {url}")
    
    try:
        async with websockets.connect(url) as ws:
            print("✅ Connected! Receiving market data...")
            print()
            
            # Receive messages
            message_count = 0
            while message_count < 10:  # Receive 10 messages then stop
                message = await ws.recv()
                data = json.loads(message)
                
                print(f"📥 {data['symbol']:6} ${data['price']:7.2f}  {data['timestamp']}")
                
                message_count += 1
            
            print("\n✅ Received 10 updates, disconnecting")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure server is running: python examples/simple_ws_server.py")


if __name__ == "__main__":
    asyncio.run(receive_market_data())