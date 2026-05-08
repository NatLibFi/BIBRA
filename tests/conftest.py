"""Test configuration and fixtures."""

import asyncio
import pytest
from fastapi.testclient import TestClient

from bibra.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class AsyncHelpers:
    """Helper methods for async testing with pytest fixtures."""

    @staticmethod
    def async_mock(return_value):
        """Create an async mock that returns the specified value."""
        mock = pytest.MagicMock()
        mock.return_value = return_value
        return mock

    @staticmethod
    def run_async(coro, *args, **kwargs):
        """Run an async coroutine in the current event loop."""
        return asyncio.get_event_loop().run_until_complete(coro(*args, **kwargs))


# Register helpers so they're accessible as pytest.helpers
pytest.helpers = AsyncHelpers
