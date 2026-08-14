"""Tests for API routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

from bibra.api.v0.routes import (
    extract,
    extract_url,
    get_registry,
    list_projects,
    router,
)
from bibra.config import ConfigError, ProjectNotFoundError, ProjectRegistry
from bibra.types import PublicationMetadata


class TestAPIRoutes:
    """Tests for API v0 routes."""

    def test_root_route_exists(self):
        """The router should have a root route."""
        assert len(router.routes) >= 1

    def test_projects_route_exists(self):
        """The router should have a projects route."""
        routes = [str(r.path) for r in router.routes]
        assert "/projects" in routes

    async def test_list_projects_returns_projects(self):
        """The /projects endpoint should return configured projects."""
        from bibra.config import ProjectRegistry

        registry = ProjectRegistry()
        result = await list_projects(registry=registry)
        assert "projects" in result
        # Should have the default project from tests/projects.toml
        project_ids = [p["id"] for p in result["projects"]]
        assert "dummy" in project_ids

    def test_extract_route_exists(self):
        """The router should have a project-specific extract route."""
        routes = [str(r.path) for r in router.routes]
        assert "/projects/{project_id}/extract" in routes

    def test_extract_route_is_post_method(self):
        """The extract route should use POST method."""
        extract_routes = [
            r for r in router.routes if str(r.path) == "/projects/{project_id}/extract"
        ]
        assert len(extract_routes) >= 1
        # Check that the route uses POST method
        route = extract_routes[0]
        assert isinstance(route, APIRoute)

    async def test_extract_returns_example_metadata(self):
        """The /projects/{project_id}/extract endpoint should return example
        publication metadata."""
        from bibra.config import ProjectRegistry

        registry = ProjectRegistry()
        # Use dummy backend for testing (no API calls needed)
        result = await extract(project_id="dummy", files=[], registry=registry)

        assert isinstance(result, PublicationMetadata)
        assert result.language == "en"
        assert (
            result.title == "Machine Learning Approaches for Software Defect Prediction"
        )
        assert result.creator == ["Smith, John", "Johnson, Emily"]
        assert result.year == "2023"
        assert result.publisher == ["Springer", "ACM"]
        assert result.doi == "10.1234/example.doi.12345"
        assert result.e_isbn == ["978-0-123456-78-9"]
        assert result.type_coar == "article"

        # Verify fields that don't have values are None or empty lists
        assert result.alt_title is None
        assert result.p_isbn == []
        assert result.e_issn is None

    def test_extract_url_route_exists(self):
        """The router should have a project-specific extract-url route."""
        routes = [str(r.path) for r in router.routes]
        assert "/projects/{project_id}/extract-url" in routes

    def test_extract_url_route_is_post_method(self):
        """The extract-url route should use POST method."""
        extract_url_routes = [
            r
            for r in router.routes
            if str(r.path) == "/projects/{project_id}/extract-url"
        ]
        assert len(extract_url_routes) >= 1
        # Check that the route uses POST method
        route = extract_url_routes[0]
        assert isinstance(route, APIRoute)

    async def test_extract_url_returns_example_metadata(self):
        """The /projects/{project_id}/extract-url endpoint should return example
        publication metadata."""
        from pydantic import HttpUrl

        registry = ProjectRegistry()

        # Mock httpx.AsyncClient stream response
        mock_response = MagicMock()
        mock_response.headers.get.return_value = "application/pdf"
        mock_response.status_code = 200

        async def mock_aiter_bytes(*args, **kwargs):
            yield b"%PDF-1.4 mock content"

        mock_response.aiter_bytes.return_value = mock_aiter_bytes()
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = False

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = False
            mock_client.stream = MagicMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await extract_url(
                project_id="dummy",
                registry=registry,
                url=HttpUrl("https://example.com/paper.pdf"),
            )

        assert isinstance(result, PublicationMetadata)
        assert result.language == "en"
        assert (
            result.title == "Machine Learning Approaches for Software Defect Prediction"
        )
        assert result.creator == ["Smith, John", "Johnson, Emily"]
        assert result.year == "2023"
        assert result.publisher == ["Springer", "ACM"]
        assert result.doi == "10.1234/example.doi.12345"
        assert result.e_isbn == ["978-0-123456-78-9"]
        assert result.type_coar == "article"
        # Verify fields that don't have values are None or empty lists
        assert result.alt_title is None
        assert result.p_isbn == []
        assert result.e_issn is None

    def test_get_registry_returns_existing_registry(self):
        """get_registry should return the registry already on app.state."""
        mock_state = MagicMock()
        mock_state.project_registry = ProjectRegistry("tests/projects.toml")
        mock_app = MagicMock()
        mock_app.state = mock_state
        request = MagicMock(spec=Request)
        request.app = mock_app

        result = get_registry(request)
        assert result is mock_state.project_registry

    def test_get_registry_lazy_initializes_when_missing(self):
        """Lazily create and load a registry when not on app.state."""
        mock_state = MagicMock(spec=[])  # Empty spec so getattr returns None
        mock_app = MagicMock()
        mock_app.state = mock_state
        request = MagicMock(spec=Request)
        request.app = mock_app

        result = get_registry(request)
        assert isinstance(result, ProjectRegistry)
        # Verify it was attached back to app.state
        assert mock_app.state.project_registry is result
        # Verify .load() was called (projects populated from tests/projects.toml)
        assert len(result._projects) > 0

    def test_get_registry_lazy_load_fails_on_bad_config(self, monkeypatch):
        """get_registry should raise ConfigFileNotFoundError for missing config."""
        from bibra.config import ConfigFileNotFoundError

        monkeypatch.setenv("BIBRA_CONFIG", "nonexistent-path/projects.toml")
        mock_state = MagicMock(spec=[])
        mock_app = MagicMock()
        mock_app.state = mock_state
        request = MagicMock(spec=Request)
        request.app = mock_app

        with pytest.raises(ConfigFileNotFoundError):
            get_registry(request)

    async def test_list_projects_handles_config_error(self):
        """list_projects should raise HTTPException 500 on ConfigError."""
        registry = MagicMock(spec=ProjectRegistry)
        registry.list_projects.side_effect = ConfigError("Database unavailable")

        with pytest.raises(HTTPException) as exc_info:
            await list_projects(registry=registry)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Database unavailable"

    async def test_extract_handles_config_error_from_get_backend(self):
        """extract should raise HTTPException 500 on ConfigError from get_backend."""
        registry = MagicMock(spec=ProjectRegistry)
        registry.get_backend.side_effect = ConfigError("Invalid backend config")

        with pytest.raises(HTTPException) as exc_info:
            await extract(project_id="bad_project", files=[], registry=registry)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Invalid backend config"

    async def test_extract_handles_project_not_found_error(self):
        """extract should raise HTTPException 404 on ProjectNotFoundError."""
        registry = MagicMock(spec=ProjectRegistry)
        registry.get_backend.side_effect = ProjectNotFoundError(
            "Project 'unknown' not found"
        )

        with pytest.raises(HTTPException) as exc_info:
            await extract(project_id="unknown", files=[], registry=registry)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Project 'unknown' not found"
