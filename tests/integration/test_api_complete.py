"""
Integration tests for FastAPI endpoints.

Tests the complete API with real query service integration.
"""

import pytest
from fastapi.testclient import TestClient
from trading_system.api.main import app

# FASTAPI TESTING: TestClient provides sync test interface for async app
client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint returns API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_openapi_schema():
    """Test OpenAPI schema is generated."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
    # Should have our endpoints
    assert "/api/v1/strategies/" in schema["paths"]
    assert "/api/v1/backtests/" in schema["paths"]
    assert "/api/v1/auth/token" in schema["paths"]


def test_authentication_flow():
    """Test complete authentication flow."""
    # 1. Get token
    response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "trader1",
            "password": "password123"
        }
    )
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    
    token = token_data["access_token"]
    
    # 2. Use token to access protected endpoint
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "trader1"
    
    # 3. Try without token (should fail)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_invalid_credentials():
    """Test authentication fails with invalid credentials."""
    response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "invalid",
            "password": "wrong"
        }
    )
    assert response.status_code == 401


@pytest.mark.skip(reason="Requires Day 7 data to be populated")
def test_list_strategies():
    """Test listing strategies (requires Day 7 setup)."""
    response = client.get("/api/v1/strategies/")
    assert response.status_code == 200
    data = response.json()
    assert "strategies" in data
    assert "total" in data


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])