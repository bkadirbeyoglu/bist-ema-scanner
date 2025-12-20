"""
WebSocket handler for real-time paper trading updates.

Uses contextlib.suppress for clean exception handling in cleanup code.
"""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import APIRouter
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi import status


class MessageType(str, Enum):
    """WebSocket message types."""
    CONNECTED = "connected"
    PORTFOLIO_UPDATE = "portfolio_update"
    TRADE_EXECUTED = "trade_executed"
    PONG = "pong"
    SUBSCRIBED = "subscribed"
    ERROR = "error"
    PING = "ping"
    SUBSCRIBE = "subscribe"


# ============================================================================
# CONNECTION MANAGER
# ============================================================================

class ConnectionManager:
    """
    Manages WebSocket connections for paper trading sessions.
    
    Responsibilities:
    - Track connections per session
    - Handle subscriptions
    - Broadcast updates to connected clients
    """
    
    def __init__(self) -> None:
        """Initialize the connection manager."""
        # session_id → list of WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        
        # WebSocket → set of subscribed channels
        self._subscriptions: dict[WebSocket, set[str]] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
    ) -> None:
        """
        Accept a WebSocket connection for a session.
        
        Args:
            websocket: The WebSocket connection
            session_id: The paper trading session ID
        """
        await websocket.accept()
        
        # Register connection
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(websocket)
        
        # Default subscriptions (all channels)
        self._subscriptions[websocket] = {"portfolio", "trades", "prices"}
        
        # Send connected message
        await self._send_message(
            websocket,
            {
                "type": MessageType.CONNECTED.value,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    
    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove a WebSocket connection using suppress for clean exception handling."""
        with suppress(ValueError, KeyError):
            self._connections[session_id].remove(websocket)
        with suppress(KeyError):
            del self._subscriptions[websocket]
    
    async def broadcast_to_session(
        self,
        session_id: str,
        message: dict[str, Any],
        channel: str = "portfolio",
    ) -> None:
        """
        Broadcast a message to all connections for a session.
        
        Only sends to clients subscribed to the specified channel.
        """
        connections = self._connections.get(session_id, [])
        
        for websocket in connections:
            subscriptions = self._subscriptions.get(websocket, set())
            if channel in subscriptions:
                await self._send_message(websocket, message)
    
    async def send_portfolio_update(
        self,
        session_id: str,
        portfolio_data: dict,
    ) -> None:
        """Send portfolio update to all session connections."""
        await self.broadcast_to_session(
            session_id,
            {
                "type": MessageType.PORTFOLIO_UPDATE.value,
                "data": portfolio_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            channel="portfolio",
        )
    
    async def send_trade_executed(
        self,
        session_id: str,
        trade_data: dict,
    ) -> None:
        """Send trade execution notification."""
        await self.broadcast_to_session(
            session_id,
            {
                "type": MessageType.TRADE_EXECUTED.value,
                "data": trade_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            channel="trades",
        )
    
    def update_subscriptions(
        self,
        websocket: WebSocket,
        channels: list[str],
    ) -> set[str]:
        """
        Update channel subscriptions for a WebSocket.
        
        Returns the set of valid subscribed channels.
        """
        valid_channels = {"portfolio", "trades", "prices"}
        subscribed = set(channels) & valid_channels
        self._subscriptions[websocket] = subscribed
        return subscribed
    
    async def _send_message(
        self,
        websocket: WebSocket,
        message: dict[str, Any],
    ) -> None:
        """
        Send a JSON message, handling Decimal serialization.
        
        Silently ignores send failures (connection might be closed).
        """
        def decimal_serializer(obj: Any) -> float:
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        with suppress(Exception):
            await websocket.send_text(
                json.dumps(message, default=decimal_serializer)
            )


# Global connection manager instance
connection_manager = ConnectionManager()


# ============================================================================
# WEBSOCKET ROUTER
# ============================================================================

ws_router = APIRouter()


@ws_router.websocket("/ws/sessions/{session_id}")
async def websocket_session_endpoint(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    WebSocket endpoint for real-time session updates.
    
    Protocol:
    ─────────
    
    Client → Server:
    - {"type": "ping"}                           → Heartbeat request
    - {"type": "subscribe", "channels": [...]}   → Subscribe to channels
    
    Server → Client:
    - {"type": "connected", "session_id": "..."}  → Connection confirmed
    - {"type": "portfolio_update", "data": {...}} → Portfolio changed
    - {"type": "trade_executed", "data": {...}}   → Trade completed
    - {"type": "pong"}                            → Heartbeat response
    - {"type": "subscribed", "channels": [...]}   → Subscription confirmed
    - {"type": "error", "message": "..."}         → Error occurred
    """
    # Import here to avoid circular dependency
    # pylint: disable=import-outside-toplevel
    from paper_trading_service.api.router import get_session_manager
    
    manager = get_session_manager()
    session = manager.get_session(session_id)
    
    # Validate session exists
    if session is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Accept connection
    await connection_manager.connect(websocket, session_id)
    
    try:
        # Send initial portfolio snapshot
        # Build prices dict from positions (use entry_price as placeholder)
        prices: dict[str, Decimal] = {}
        for symbol in session.portfolio.symbols:
            pos = session.portfolio.get_position(symbol)
            if pos:
                prices[symbol] = pos.entry_price
        snapshot = session.portfolio.snapshot(prices)
        await connection_manager.send_portfolio_update(session_id, snapshot)
        
        # Message handling loop
        while True:
            try:
                data = await websocket.receive_json()
                await _handle_client_message(websocket, session_id, data)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON format")
    
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, session_id)
    except Exception:
        connection_manager.disconnect(websocket, session_id)
        with suppress(Exception):
            await websocket.close()


async def _handle_client_message(
    websocket: WebSocket,
    session_id: str,
    data: dict[str, Any],
) -> None:
    """Handle an incoming message from the client."""
    message_type = data.get("type", "").lower()
    
    if message_type == "ping":
        await websocket.send_json({
            "type": MessageType.PONG.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    elif message_type == "subscribe":
        channels = data.get("channels", [])
        subscribed = connection_manager.update_subscriptions(websocket, channels)
        await websocket.send_json({
            "type": MessageType.SUBSCRIBED.value,
            "channels": list(subscribed),
        })
    
    else:
        await _send_error(websocket, f"Unknown message type: {message_type}")


async def _send_error(websocket: WebSocket, message: str) -> None:
    """Send an error message to the client."""
    with suppress(Exception):
        await websocket.send_json({
            "type": MessageType.ERROR.value,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ============================================================================
# PUBLIC FUNCTIONS FOR BROADCASTING
# ============================================================================

async def notify_trade_executed(session_id: str, trade_data: dict) -> None:
    """
    Notify all connected clients about a trade execution.
    
    Call this from the order execution flow.
    """
    await connection_manager.send_trade_executed(session_id, trade_data)


async def notify_portfolio_update(session_id: str, portfolio_data: dict) -> None:
    """
    Notify all connected clients about a portfolio update.
    
    Call this after trades or price updates.
    """
    await connection_manager.send_portfolio_update(session_id, portfolio_data)