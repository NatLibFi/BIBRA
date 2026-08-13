"""Test configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

from bibra.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def set_test_config(monkeypatch: pytest.MonkeyPatch):
    """Ensure all tests use the test config file."""
    # Per-test override for tests creating their own ProjectRegistry()
    monkeypatch.setenv("BIBRA_CONFIG", "tests/projects.toml")
