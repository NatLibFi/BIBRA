"""Integration tests using TestClient."""

import pytest
from fastapi.testclient import TestClient

from bibra.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_returns_html(self, client):
        """Root endpoint should return HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_root_has_expected_content(self, client):
        """Root should return the index.html content."""
        response = client.get("/")
        assert response.status_code == 200
        # Check that it contains some expected HTML elements
        assert "<html" in response.text or "<!DOCTYPE" in response.text


class TestAPIV0Root:
    """Tests for API v0 root endpoint."""

    def test_api_v0_root_exists(self, client):
        """API v0 root should exist."""
        response = client.get("/v0/")
        assert response.status_code == 200

    def test_api_v0_root_returns_json(self, client):
        """API v0 root should return JSON."""
        response = client.get("/v0/")
        assert response.headers["content-type"] == "application/json"

    def test_api_v0_root_has_version(self, client):
        """API v0 root should return version info."""
        response = client.get("/v0/")
        data = response.json()
        assert "version" in data
        assert "message" in data
