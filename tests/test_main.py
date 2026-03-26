"""Tests for main FastAPI application."""

from fastapi import FastAPI


class TestMainApp:
    """Tests for the main FastAPI application."""

    def test_app_is_fastapi_instance(self):
        """The app should be a FastAPI instance."""
        from bibra.main import app

        assert isinstance(app, FastAPI)

    def test_app_has_title(self):
        """The app should have a title."""
        from bibra.main import app

        assert app.title == "BIBRA API"

    def test_app_has_version(self):
        """The app should have a version."""
        from bibra.main import app

        assert app.version is not None
