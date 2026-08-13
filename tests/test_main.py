"""Tests for main FastAPI application."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bibra.config import ConfigFileNotFoundError, ProjectRegistry
from bibra.main import app


class TestMainApp:
    """Tests for the main FastAPI application."""

    def test_app_is_fastapi_instance(self):
        """The app should be a FastAPI instance."""

        assert isinstance(app, FastAPI)

    def test_app_has_title(self):
        """The app should have a title."""

        assert app.title == "BIBRA API"

    def test_app_has_version(self):
        """The app should have a version."""

        assert app.version is not None

    def test_startup_loads_registry(self):
        """Startup should initialize and load the project registry."""
        # TestClient triggers the ASGI lifespan, which runs startup_event
        with TestClient(app):
            registry = getattr(app.state, "project_registry", None)
            assert isinstance(registry, ProjectRegistry)
            # _projects being non-empty proves .load() was called at startup
            assert len(registry._projects) > 0


class TestStartupFailure:
    """Tests for startup failure when config is invalid."""

    @pytest.mark.asyncio
    async def test_startup_fails_on_missing_config_file(self, monkeypatch):
        """Startup should raise ConfigFileNotFoundError for missing config."""
        from bibra.main import startup_event

        monkeypatch.setenv("BIBRA_CONFIG", "nonexistent-path/projects.toml")
        # Reset app state so that startup_event will attempt a fresh load.
        if hasattr(app.state, "project_registry"):
            delattr(app.state, "project_registry")
        with pytest.raises(ConfigFileNotFoundError):
            await startup_event()
