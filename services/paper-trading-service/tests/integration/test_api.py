"""
Integration tests for Paper Trading REST API.

Uses FastAPI TestClient to test complete request/response cycles.

These tests verify:
- Request validation
- Response format
- HTTP status codes
- Session lifecycle
- Error handling

Note: Fixtures (client, session_id, running_session_id) are defined
in tests/conftest.py and automatically available here.
"""

from fastapi.testclient import TestClient


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================

class TestHealthCheck:
    """Test the health check endpoint."""
    
    def test_health_check_returns_healthy(self, client: TestClient) -> None:
        """GET /api/v1/health should return healthy status."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "paper-trading-service"
        assert "active_sessions" in data


# ============================================================================
# SESSION CRUD TESTS
# ============================================================================

class TestCreateSession:
    """Test session creation endpoint."""
    
    def test_create_session_with_defaults(self, client: TestClient) -> None:
        """POST /api/v1/sessions with minimal data should work."""
        response = client.post(
            "/api/v1/sessions",
            json={"initial_cash": "100000.00"},
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert data["state"] == "IDLE"
        assert float(data["initial_cash"]) == 100000.0
    
    def test_create_session_duplicate_id_returns_409(
        self, client: TestClient, session_id: str
    ) -> None:
        """Creating session with existing ID should return 409 Conflict."""
        response = client.post(
            "/api/v1/sessions",
            json={
                "initial_cash": "100000.00",
                "session_id": session_id,
            },
        )
        
        assert response.status_code == 409
    
    def test_create_session_invalid_cash_returns_422(
        self, client: TestClient
    ) -> None:
        """Initial cash below minimum should return 422."""
        response = client.post(
            "/api/v1/sessions",
            json={"initial_cash": "100.00"},  # Below $1000 minimum
        )
        
        assert response.status_code == 422


class TestGetSession:
    """Test session retrieval endpoints."""
    
    def test_get_session_by_id(
        self, client: TestClient, session_id: str
    ) -> None:
        """GET /api/v1/sessions/{id} should return session details."""
        response = client.get(f"/api/v1/sessions/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["state"] == "IDLE"
    
    def test_get_nonexistent_session_returns_404(
        self, client: TestClient
    ) -> None:
        """Getting non-existent session should return 404."""
        response = client.get("/api/v1/sessions/nonexistent-id")
        
        assert response.status_code == 404
    
    def test_list_sessions(
        self, client: TestClient, session_id: str
    ) -> None:
        """GET /api/v1/sessions should list all sessions."""
        # Create another session
        client.post("/api/v1/sessions", json={"initial_cash": "50000.00"})
        
        response = client.get("/api/v1/sessions")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        assert len(data["sessions"]) >= 2


class TestDeleteSession:
    """Test session deletion endpoint."""
    
    def test_delete_session(
        self, client: TestClient, session_id: str
    ) -> None:
        """DELETE /api/v1/sessions/{id} should remove the session."""
        response = client.delete(f"/api/v1/sessions/{session_id}")
        
        assert response.status_code == 204
        
        # Verify it's gone
        get_response = client.get(f"/api/v1/sessions/{session_id}")
        assert get_response.status_code == 404
    
    def test_delete_nonexistent_returns_404(self, client: TestClient) -> None:
        """Deleting non-existent session should return 404."""
        response = client.delete("/api/v1/sessions/nonexistent-id")
        
        assert response.status_code == 404


# ============================================================================
# SESSION LIFECYCLE TESTS
# ============================================================================

class TestSessionLifecycle:
    """Test session start/stop endpoints."""
    
    def test_start_session(
        self, client: TestClient, session_id: str
    ) -> None:
        """POST /api/v1/sessions/{id}/start should start the session."""
        response = client.post(f"/api/v1/sessions/{session_id}/start")
        
        assert response.status_code == 200
        assert response.json()["state"] == "RUNNING"
    
    def test_stop_session(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """POST /api/v1/sessions/{id}/stop should stop the session."""
        response = client.post(f"/api/v1/sessions/{running_session_id}/stop")
        
        assert response.status_code == 200
        assert response.json()["state"] == "STOPPED"


# ============================================================================
# PORTFOLIO TESTS
# ============================================================================

class TestPortfolio:
    """Test portfolio retrieval endpoint."""
    
    def test_get_portfolio(
        self, client: TestClient, session_id: str
    ) -> None:
        """GET /api/v1/sessions/{id}/portfolio should return snapshot."""
        response = client.get(f"/api/v1/sessions/{session_id}/portfolio")
        
        assert response.status_code == 200
        data = response.json()
        assert float(data["cash"]) == 100000.0
        assert data["positions"] == []
        assert float(data["total_pnl"]) == 0.0


# ============================================================================
# ORDER EXECUTION TESTS
# ============================================================================

class TestOrderExecution:
    """Test order submission endpoint."""
    
    def test_submit_buy_order(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """POST /api/v1/sessions/{id}/orders should execute buy order."""
        response = client.post(
            f"/api/v1/sessions/{running_session_id}/orders",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 100,
                "market_price": "150.00",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["symbol"] == "AAPL"
        assert data["quantity"] == 100
        assert data["executed_price"] is not None
    
    def test_submit_order_to_stopped_session_returns_400(
        self, client: TestClient, session_id: str
    ) -> None:
        """Submitting order to non-running session should return 400."""
        response = client.post(
            f"/api/v1/sessions/{session_id}/orders",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 100,
                "market_price": "150.00",
            },
        )
        
        assert response.status_code == 400
    
    def test_submit_order_invalid_quantity_returns_422(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Order with invalid quantity should return 422."""
        response = client.post(
            f"/api/v1/sessions/{running_session_id}/orders",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 0,  # Invalid
                "market_price": "150.00",
            },
        )
        
        assert response.status_code == 422
    
    def test_submit_order_invalid_symbol_returns_422(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Order with invalid symbol should return 422."""
        response = client.post(
            f"/api/v1/sessions/{running_session_id}/orders",
            json={
                "symbol": "invalid123",  # Invalid pattern
                "side": "BUY",
                "quantity": 100,
                "market_price": "150.00",
            },
        )
        
        assert response.status_code == 422


# ============================================================================
# TRADE HISTORY TESTS
# ============================================================================

class TestTradeHistory:
    """Test trade history endpoint."""
    
    def test_get_trades_empty(
        self, client: TestClient, session_id: str
    ) -> None:
        """New session should have no trades."""
        response = client.get(f"/api/v1/sessions/{session_id}/trades")
        
        assert response.status_code == 200
        assert response.json() == []
    
    def test_get_trades_after_execution(
        self, client: TestClient, running_session_id: str
    ) -> None:
        """Should return trades after execution."""
        # Execute a trade
        client.post(
            f"/api/v1/sessions/{running_session_id}/orders",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 100,
                "market_price": "150.00",
            },
        )
        
        # Get trades
        response = client.get(f"/api/v1/sessions/{running_session_id}/trades")
        
        assert response.status_code == 200
        trades = response.json()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "AAPL"
        assert trades[0]["side"] == "BUY"
        assert trades[0]["quantity"] == 100