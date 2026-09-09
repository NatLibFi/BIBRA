"""Tests for API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
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
from bibra.net_security import ProxyRequiredError, UrlPolicyError
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
        route = extract_url_routes[0]
        assert isinstance(route, APIRoute)
        assert "POST" in route.methods

    async def test_extract_url_returns_example_metadata(self, monkeypatch):
        """The /projects/{project_id}/extract-url endpoint should return example
        publication metadata."""
        from pydantic import HttpUrl

        registry = ProjectRegistry()
        monkeypatch.setenv("BIBRA_URL_PROXY", "direct")

        with patch(
            "bibra.api.v0.routes.fetch_file",
            new=AsyncMock(return_value=b"%PDF-1.4 mock content"),
        ) as mock_fetch:
            result = await extract_url(
                project_id="dummy",
                registry=registry,
                url=HttpUrl("https://example.com/paper.pdf"),
            )

        mock_fetch.assert_awaited_once()
        args, _ = mock_fetch.call_args
        assert args[0] == "https://example.com/paper.pdf"
        assert args[1].proxy == "direct"

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

    async def test_extract_url_uses_configured_proxy(self, monkeypatch):
        """The fetch policy passed to fetch_file carries the configured proxy."""
        from pydantic import HttpUrl

        monkeypatch.setenv("BIBRA_URL_PROXY", "http://proxy.example.com:8080")

        registry = ProjectRegistry()

        with patch(
            "bibra.api.v0.routes.fetch_file",
            new=AsyncMock(return_value=b"%PDF-1.4 mock content"),
        ) as mock_fetch:
            result = await extract_url(
                project_id="dummy",
                registry=registry,
                url=HttpUrl("https://example.com/paper.pdf"),
            )

        args, _ = mock_fetch.call_args
        assert args[1].proxy == "http://proxy.example.com:8080"
        assert isinstance(result, PublicationMetadata)

    async def test_extract_url_refused_when_proxy_not_set(self, monkeypatch):
        """With no proxy/direct configured the endpoint returns 503."""
        from pydantic import HttpUrl

        monkeypatch.delenv("BIBRA_URL_PROXY", raising=False)

        registry = ProjectRegistry()

        with (
            patch(
                "bibra.api.v0.routes.fetch_file",
                new=AsyncMock(
                    side_effect=ProxyRequiredError(ProxyRequiredError.MESSAGE)
                ),
            ) as mock_fetch,
            pytest.raises(HTTPException) as exc_info,
        ):
            await extract_url(
                project_id="dummy",
                registry=registry,
                url=HttpUrl("https://example.com/paper.pdf"),
            )

        mock_fetch.assert_awaited_once()
        assert exc_info.value.status_code == 503
        assert "BIBRA_URL_PROXY" in exc_info.value.detail

    async def test_extract_url_policy_error_returns_400(self, monkeypatch):
        """A URL rejected by the fetch policy returns 400 with a generic detail."""
        from pydantic import HttpUrl

        monkeypatch.setenv("BIBRA_URL_PROXY", "direct")

        registry = ProjectRegistry()

        with (
            patch(
                "bibra.api.v0.routes.fetch_file",
                new=AsyncMock(
                    side_effect=UrlPolicyError("URL rejected by fetch policy")
                ),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await extract_url(
                project_id="dummy",
                registry=registry,
                url=HttpUrl("http://169.254.169.254/latest/meta-data/"),
            )

        assert exc_info.value.status_code == 400
        assert "169.254.169.254" not in exc_info.value.detail

    async def test_extract_url_http_error_returns_502(self, monkeypatch):
        """A failed download returns 502 without leaking internal details."""
        from pydantic import HttpUrl

        monkeypatch.setenv("BIBRA_URL_PROXY", "direct")

        registry = ProjectRegistry()

        with (
            patch(
                "bibra.api.v0.routes.fetch_file",
                new=AsyncMock(
                    side_effect=httpx2.HTTPError("connection refused to internal host")
                ),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await extract_url(
                project_id="dummy",
                registry=registry,
                url=HttpUrl("https://example.com/paper.pdf"),
            )

        assert exc_info.value.status_code == 502
        assert "internal" not in exc_info.value.detail

    async def test_extract_url_cleanup_temp_file_on_backend_error(self, monkeypatch):
        """The temporary file is removed even if the backend raises."""
        from pydantic import HttpUrl

        monkeypatch.setenv("BIBRA_URL_PROXY", "direct")

        registry = ProjectRegistry()
        mock_backend = MagicMock()
        mock_backend.extract = AsyncMock(side_effect=RuntimeError("boom"))
        registry.get_backend = MagicMock(return_value=mock_backend)

        with (
            patch(
                "bibra.api.v0.routes.fetch_file",
                new=AsyncMock(return_value=b"%PDF-1.4 mock content"),
            ),
            patch("bibra.api.v0.routes.os.unlink") as mock_unlink,
            pytest.raises(RuntimeError, match="boom"),
        ):
            await extract_url(
                project_id="dummy",
                registry=registry,
                url=HttpUrl("https://example.com/paper.pdf"),
            )

        mock_unlink.assert_called_once()
