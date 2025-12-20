"""
Integration tests for Paper Trading WebSocket streaming.

Tests real-time portfolio updates via WebSocket connections.

IMPORTANT: These tests depend on the REST API working correctly.
Run test_api.py first to ensure REST endpoints are functional.

Note: Fixtures (client, running_session_id) are defined in
tests/conftest.py and automatically available here.
"""

import pytest
from fastapi.testclient import TestClient


# ============================================================================
# CONNECTION TESTS
# ============================================================================

class TestWebSocketConnection:
    """Test WebSocket connection handling."""
    
    def test_connect_to_valid_session(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Should connect to a valid session and receive connected message."""
        with client.websocket_connect(
            f"/ws/sessions/{running_session_id}"
        ) as websocket:
            # Should receive connected message
            data = websocket.receive_json()
            assert data["type"] == "connected"
            assert data["session_id"] == running_session_id
    
    def test_connect_to_nonexistent_session_closes(
        self, client: TestClient
    ) -> None:
        """Connecting to non-existent session should close connection."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/sessions/nonexistent") as ws:
                ws.receive_json()  # Should not get here
    
    def test_receive_initial_portfolio(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Should receive portfolio snapshot after connecting."""
        with client.websocket_connect(
            f"/ws/sessions/{running_session_id}"
        ) as websocket:
            # First: connected message
            websocket.receive_json()
            
            # Second: portfolio snapshot
            data = websocket.receive_json()
            assert data["type"] == "portfolio_update"
            assert "cash" in data["data"]
            assert "total_value" in data["data"]


# ============================================================================
# MESSAGE HANDLING TESTS
# ============================================================================

class TestWebSocketMessages:
    """Test WebSocket message handling."""
    
    def test_ping_pong(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Should respond to ping with pong."""
        with client.websocket_connect(
            f"/ws/sessions/{running_session_id}"
        ) as websocket:
            # Skip initial messages
            websocket.receive_json()  # connected
            websocket.receive_json()  # portfolio
            
            # Send ping
            websocket.send_json({"type": "ping"})
            
            # Receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"
    
    def test_subscribe_to_channels(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Should acknowledge subscription requests."""
        with client.websocket_connect(
            f"/ws/sessions/{running_session_id}"
        ) as websocket:
            # Skip initial messages
            websocket.receive_json()
            websocket.receive_json()
            
            # Subscribe to specific channels
            websocket.send_json({
                "type": "subscribe",
                "channels": ["trades", "portfolio"],
            })
            
            # Receive subscription confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert "trades" in data["channels"]
            assert "portfolio" in data["channels"]
    
    def test_invalid_message_returns_error(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Should return error for invalid message type."""
        with client.websocket_connect(
            f"/ws/sessions/{running_session_id}"
        ) as websocket:
            # Skip initial messages
            websocket.receive_json()
            websocket.receive_json()
            
            # Send unknown message type
            websocket.send_json({"type": "unknown_type"})
            
            # Receive error
            data = websocket.receive_json()
            assert data["type"] == "error"


# ============================================================================
# REAL-TIME UPDATE TESTS
# ============================================================================

class TestRealTimeUpdates:
    """Test real-time updates via WebSocket."""
    
    @pytest.mark.skip(reason="Requires REST-to-WebSocket integration not yet implemented")
    def test_receive_trade_notification(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Should receive notification when trade is executed.
        
        NOTE: This test requires the REST order endpoint to broadcast
        trade notifications to connected WebSocket clients. This integration
        will be implemented when we add the SQS consumer that processes
        signals and broadcasts to WebSockets.
        """
        with client.websocket_connect(
            f"/ws/sessions/{running_session_id}"
        ) as websocket:
            # Skip initial messages
            websocket.receive_json()  # connected
            websocket.receive_json()  # portfolio
            
            # Execute a trade via REST API
            client.post(
                f"/api/v1/sessions/{running_session_id}/orders",
                json={
                    "symbol": "AAPL",
                    "side": "BUY",
                    "quantity": 100,
                    "market_price": "150.00",
                },
            )
            
            # Should receive update (trade or portfolio)
            data = websocket.receive_json()
            assert data["type"] in ["trade_executed", "portfolio_update"]