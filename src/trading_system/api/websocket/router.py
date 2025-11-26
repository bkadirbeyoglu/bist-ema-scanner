"""
WebSocket router for real-time trading updates.

Endpoints:
- /ws/echo - Test (no auth)
- /ws/signals - All signals (requires auth)
- /ws/strategies/{id} - Strategy updates (requires auth)
- /ws/market-data/{symbol} - Price stream (requires auth)

Authentication:
    ws://localhost:8000/ws/signals?token=YOUR_JWT_TOKEN
"""
import uuid
import random
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from trading_system.api.websocket.manager import manager
from trading_system.api.websocket.schemas import (
    WSMessageType,
    SignalMessage,
    MarketDataMessage,
    SignalType,
)
from trading_system.api.websocket.auth import get_current_user_ws

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


# ============================================================
# ECHO - No Authentication (Testing Only)
# ============================================================

@router.websocket("/echo")
async def websocket_echo(websocket: WebSocket):
    """Echo endpoint for testing. No authentication required."""
    await websocket.accept()
    logger.info("Echo WebSocket connected")
    
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({
                "type": "echo",
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            })
    except WebSocketDisconnect:
        logger.info("Echo WebSocket disconnected")


# ============================================================
# SIGNALS - Authenticated
# ============================================================

@router.websocket("/signals")
async def websocket_signals(websocket: WebSocket):
    """
    Stream all strategy signals. Requires JWT authentication.
    
    Usage:
        ws://localhost:8000/ws/signals?token=eyJ...
        
    Then send:
        {"type": "subscribe", "topics": ["signals"]}
    """
    # Authenticate (accepts connection or closes with error)
    username = await get_current_user_ws(websocket)
    if username is None:
        return  # Connection closed by auth
    
    client_id = f"signals_{uuid.uuid4().hex[:8]}"
    
    # Register with manager (connection already accepted by auth)
    async with manager._lock:
        manager.active_connections[client_id] = websocket
        manager.client_users[client_id] = username
        manager.subscriptions[client_id] = set()
        manager.connection_times[client_id] = datetime.utcnow()
    
    logger.info(f"Signals connected: {client_id} (user: {username})")
    
    # Welcome message
    await websocket.send_json({
        "type": "connected",
        "client_id": client_id,
        "username": username,
        "available_topics": ["signals", "signals.{strategy_id}", "performance"]
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "subscribe":
                topics = data.get("topics", [])
                subscribed = manager.subscribe(client_id, topics)
                await websocket.send_json({
                    "type": "subscribed",
                    "topics": subscribed
                })
                
            elif msg_type == "unsubscribe":
                topics = data.get("topics", [])
                manager.unsubscribe(client_id, topics)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "topics": topics
                })
                
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                
            else:
                await websocket.send_json({
                    "type": "error",
                    "error": f"Unknown type: {msg_type}"
                })
                
    except WebSocketDisconnect:
        logger.info(f"Signals disconnected: {client_id}")
    finally:
        await manager.disconnect(client_id)


# ============================================================
# STRATEGY-SPECIFIC - Authenticated
# ============================================================

@router.websocket("/strategies/{strategy_id}")
async def websocket_strategy(websocket: WebSocket, strategy_id: str):
    """
    Stream updates for specific strategy. Auto-subscribes to strategy topics.
    
    Usage:
        ws://localhost:8000/ws/strategies/strategy-ma-001?token=eyJ...
    """
    username = await get_current_user_ws(websocket)
    if username is None:
        return
    
    client_id = f"strategy_{strategy_id}_{uuid.uuid4().hex[:8]}"
    
    async with manager._lock:
        manager.active_connections[client_id] = websocket
        manager.client_users[client_id] = username
        manager.subscriptions[client_id] = set()
        manager.connection_times[client_id] = datetime.utcnow()
    
    # Auto-subscribe
    topics = [f"signals.{strategy_id}", f"performance.{strategy_id}"]
    manager.subscribe(client_id, topics)
    
    await websocket.send_json({
        "type": "connected",
        "client_id": client_id,
        "strategy_id": strategy_id,
        "subscribed_topics": topics
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(client_id)


# ============================================================
# MARKET DATA - Authenticated with Price Streaming
# ============================================================

@router.websocket("/market-data/{symbol}")
async def websocket_market_data(websocket: WebSocket, symbol: str):
    """
    Stream real-time price updates for symbol.
    
    Usage:
        ws://localhost:8000/ws/market-data/AAPL?token=eyJ...
    """
    username = await get_current_user_ws(websocket)
    if username is None:
        return
    
    symbol = symbol.upper()
    client_id = f"market_{symbol}_{uuid.uuid4().hex[:8]}"
    
    async with manager._lock:
        manager.active_connections[client_id] = websocket
        manager.client_users[client_id] = username
        manager.subscriptions[client_id] = set()
        manager.connection_times[client_id] = datetime.utcnow()
    
    topic = f"market-data.{symbol}"
    manager.subscribe(client_id, [topic])
    
    await websocket.send_json({
        "type": "connected",
        "symbol": symbol,
        "message": f"Streaming {symbol} prices"
    })
    
    # Base prices for simulation
    base_prices = {"AAPL": 150.0, "GOOGL": 140.0, "MSFT": 380.0, "TSLA": 250.0}
    base_price = base_prices.get(symbol, 100.0)
    
    async def stream_prices():
        """Background task for price streaming."""
        while True:
            try:
                change = random.uniform(-0.5, 0.5)
                price = base_price + change
                
                msg = MarketDataMessage(
                    symbol=symbol,
                    price=Decimal(str(round(price, 2))),
                    bid=Decimal(str(round(price - 0.02, 2))),
                    ask=Decimal(str(round(price + 0.02, 2))),
                    volume=random.randint(10000, 100000),
                    change=Decimal(str(round(change, 2))),
                    change_percent=round(change / base_price * 100, 2)
                )
                
                await manager.broadcast_to_topic(topic, msg.model_dump(mode="json"))
                await asyncio.sleep(1.0)
                
            except asyncio.CancelledError:
                break
    
    streamer = asyncio.create_task(stream_prices())
    
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        streamer.cancel()
        await manager.disconnect(client_id)


# ============================================================
# HTTP Endpoints (REST, not WebSocket)
# ============================================================

@router.get("/stats")
async def get_stats():
    """Get WebSocket connection statistics."""
    return manager.get_stats()


@router.post("/test/publish-signal")
async def publish_test_signal(
    strategy_id: str = "strategy-ma-001",
    symbol: str = "AAPL",
    signal_type: str = "BUY",
    price: float = 150.0
):
    """
    Publish test signal to WebSocket clients.
    
    FOR TESTING - simulates strategy signal generation.
    """
    msg = SignalMessage(
        strategy_id=strategy_id,
        strategy_name="TestStrategy",
        symbol=symbol,
        signal_type=SignalType(signal_type),
        price=Decimal(str(price)),
        indicators={"test": True}
    )
    
    topic = f"signals.{strategy_id}"
    count = await manager.broadcast_to_topic(topic, msg.model_dump(mode="json"))
    
    return {"status": "published", "clients_notified": count}