"""
Shared pytest fixtures for Paper Trading Service tests.

This file is automatically discovered by pytest and makes
fixtures available to all test modules.

Fixtures provided:
- client: FastAPI TestClient with fresh app instance
- session_id: Creates a session and returns its ID
- running_session_id: Creates and starts a session, returns its ID

Usage:
    def test_something(client, session_id):
        response = client.get(f"/api/v1/sessions/{session_id}")
"""

from typing import Generator

import pytest
from fastapi.testclient import TestClient

from paper_trading_service.main import create_app
from paper_trading_service.api.router import reset_session_manager


# ============================================================================
# CORE FIXTURES
# ============================================================================

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """
    Create a test client with a fresh app instance.
    
    Resets the session manager before AND after each test
    to ensure complete isolation between tests.
    """
    reset_session_manager()  # Clean state before test
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    reset_session_manager()  # Cleanup after test


# ============================================================================
# SESSION FIXTURES
# ============================================================================

@pytest.fixture
def session_id(client: TestClient) -> str:
    """
    Create a paper trading session and return its ID.
    
    The session is in CREATED state (not started).
    """
    response = client.post(
        "/api/v1/sessions",
        json={"initial_cash": "100000.00"},
    )
    assert response.status_code == 201, f"Failed to create session: {response.text}"
    return response.json()["session_id"]


@pytest.fixture
def running_session_id(client: TestClient, session_id: str) -> str:
    """
    Create and START a paper trading session, return its ID.
    
    The session is in RUNNING state and ready for order execution.
    """
    response = client.post(f"/api/v1/sessions/{session_id}/start")
    assert response.status_code == 200, f"Failed to start session: {response.text}"
    return session_id