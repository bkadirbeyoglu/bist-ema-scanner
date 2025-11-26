"""
WebSocket authentication utilities.

IMPORTANT: WebSocket connections cannot use HTTP Authorization headers
the same way REST endpoints do. Instead, we pass the JWT token as a
query parameter in the WebSocket URL:

    ws://localhost:8000/ws/signals?token=eyJ...

This module provides authentication functions specifically for WebSocket.
"""
import logging
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect

# Import JWT utilities from Session 1
from trading_system.api.auth.jwt import decode_access_token

logger = logging.getLogger(__name__)


async def get_current_user_ws(websocket: WebSocket) -> Optional[str]:
    """
    Authenticate WebSocket connection using JWT token from query parameter.
    
    Unlike REST endpoints that use Authorization header, WebSocket
    connections pass the token in the URL query string:
    
        ws://localhost:8000/ws/signals?token=eyJhbGciOiJIUzI1NiIs...
    
    Args:
        websocket: FastAPI WebSocket connection
        
    Returns:
        Username if authenticated (connection accepted), None if rejected
        
    Behavior:
        - Success: Accepts connection, returns username
        - Failure: Accepts, sends error JSON, closes with code 4001, returns None
        
    Usage in endpoint:
        @router.websocket("/ws/signals")
        async def signals(websocket: WebSocket):
            username = await get_current_user_ws(websocket)
            if not username:
                return  # Connection already closed with error
            # Connection accepted, can send messages
            await websocket.send_json({"message": "Welcome!"})
            
    Why Query Parameter?
    - WebSocket handshake is HTTP, but after upgrade, no HTTP headers
    - Browser WebSocket API doesn't support custom headers
    - Query parameter is the standard approach
    
    Security Note:
    - Token is visible in URL (use WSS in production)
    - Token should be short-lived (30 min from Session 1)
    - Consider token refresh mechanism for long connections
    
    Important:
    - Must accept() before send_json() or close() with message
    - Rejection flow: accept → send error → close with code 4001
    """
    # Get token from query parameter
    token = websocket.query_params.get("token")
    
    if not token:
        logger.warning("WebSocket rejected: missing token")
        # Must accept before we can send error message or close properly
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "code": 4001,
            "message": "Missing authentication token"
        })
        await websocket.close(code=4001, reason="Missing token")
        return None
    
    # Validate token using Session 1's JWT utilities
    username = decode_access_token(token)
    
    if not username:
        logger.warning("WebSocket rejected: invalid token")
        await websocket.accept()
        await websocket.send_json({
            "type": "error", 
            "code": 4001,
            "message": "Invalid or expired token"
        })
        await websocket.close(code=4001, reason="Invalid token")
        return None
    
    # Accept the WebSocket connection on successful authentication
    await websocket.accept()
    logger.info(f"WebSocket authenticated: {username}")
    return username


async def require_auth_ws(websocket: WebSocket) -> str:
    """
    Require authentication for WebSocket connection.
    
    Raises WebSocketDisconnect if not authenticated.
    Use this when authentication is mandatory.
    
    Args:
        websocket: FastAPI WebSocket connection
        
    Returns:
        Username of authenticated user
        
    Raises:
        WebSocketDisconnect: If authentication fails
    """
    username = await get_current_user_ws(websocket)
    
    if not username:
        # Connection already closed with error by get_current_user_ws
        raise WebSocketDisconnect(code=4001, reason="Authentication required")
    
    return username