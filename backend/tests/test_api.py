"""Integration tests for FastAPI endpoints and error handling."""

from fastapi.testclient import TestClient
import pytest

from main import app

client = TestClient(app)


def test_root_endpoint():
    """Verify root endpoint returns service metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "version" in data
    assert data["health_check"] == "/health"


def test_health_check_endpoint():
    """Verify GET /health returns expected structure without throwing exceptions."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app_name" in data
    assert "database" in data
    assert "status" in data["database"]
    # Database status should be either connected or disconnected (never crash)
    assert data["database"]["status"] in ["connected", "disconnected"]


def test_404_not_found():
    """Verify 404 response on unknown routes."""
    response = client.get("/api/v1/non_existent_route")
    assert response.status_code == 404
