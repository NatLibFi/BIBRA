"""Test configuration and fixtures."""

import os

import pytest
from fastapi.testclient import TestClient

from bibra.main import app

# Ensure all tests use the test config file already at import time,
# before the FastAPI app is created and the project registry is initialized.
os.environ.setdefault("BIBRA_CONFIG", "tests/projects.toml")


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)
