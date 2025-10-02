# examples/simple_ws_server.py
"""
Simple WebSocket server that simulates market data.
Run this in one terminal, then connect from another.
"""

import asyncio
import websockets
import json
import random
from datetime import datetime


async def market_data_handler(websocket):
    """
    Handle WebSocket connection.
    
    This is called for each client that connects.
    Note: In newer versions of websockets library, only websocket parameter is passed.
    """
    try:
        # Get client address safely
        client_address = getattr(websocket, 'remote_address', 'unknown')
        print(f"📡 Client connected from {client_address}")
        
        # Send market data updates every second
        while True:
            # Simulate price update
            symbols = ["AAPL", "GOOGL", "MSFT"]
            symbol = random.choice(symbols)
            
            data = {
                "type": "price_update",
                "symbol": symbol,
                "price": round(random.uniform(100, 500), 2),
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to client
            await websocket.send(json.dumps(data))
            print(f"📤 Sent: {symbol} @ ${data['price']}")
            
            # Wait 1 second
            await asyncio.sleep(1)
            
    except websockets.exceptions.ConnectionClosed:
        print(f"📡 Client disconnected")
    except Exception as e:
        print(f"❌ Error in connection handler: {e}")
        # Re-raise to let websockets library handle it
        raise


async def main():
    """Start WebSocket server."""
    print("\n" + "=" * 60)
    print("Simple WebSocket Market Data Server")
    print("=" * 60)
    print("📡 Starting server on ws://localhost:8765")
    print("💡 Connect with: python examples/simple_ws_client.py")
    print()
    
    # Start server
    async with websockets.serve(market_data_handler, "localhost", 8765):
        # Keep server running
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")