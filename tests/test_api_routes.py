"""Tests for API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import HttpUrl

from bibra.api.v0.routes import (
    extract,
    extract_url,
    get_registry,
    list_projects,
    router,
)
from bibra.backend.base import BaseBackend
from bibra.config import (
    ConfigError,
    ConfigFileNotFoundError,
    ProjectNotFoundError,
    ProjectRegistry,
)
from bibra.net_security import (
    DownloadSizeExceededError,
    ProxyRequiredError,
    UnsupportedContentTypeError,
    UrlPolicyError,
)
from bibra.types import PublicationMetadata

MOCK_PDF_BYTES = b"%PDF-1.4 mock content"
DUMMY_URL = HttpUrl("https://example.com/paper.pdf")


def assert_dummy_metadata(result):
    """Assert the result equals the dummy backend's fixed example metadata."""
    assert isinstance(result, PublicationMetadata)
    assert result.language == "en"
    assert result.title == "Machine Learning Approaches for Software Defect Prediction"
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


async def _call_extract_url(monkeypatch, proxy, url, side_effect=None):
    """Configure the proxy env and mock fetch_file, then call extract_url.

    Returns (result, mock_fetch); exceptions from extract_url propagate.
    """
    if proxy is None:
        monkeypatch.delenv("BIBRA_URL_PROXY", raising=False)
    else:
        monkeypatch.setenv("BIBRA_URL_PROXY", proxy)

    kwargs = {}
    if side_effect is not None:
        kwargs["side_effect"] = side_effect
    else:
        kwargs["return_value"] = MOCK_PDF_BYTES

    with patch("bibra.api.v0.routes.fetch_file", new=AsyncMock(**kwargs)) as mock_fetch:
        result = await extract_url(
            project_id="dummy", registry=ProjectRegistry(), url=url
        )
    return result, mock_fetch


def _mock_request(state):
    """Build a mock FastAPI Request carrying the given app.state."""
    mock_app = MagicMock()
    mock_app.state = state
    request = MagicMock(spec=Request)
    request.app = mock_app
    return request


class TestAPIRoutes:
    """Tests for API v0 routes."""

    @pytest.mark.parametrize(
        ("path", "methods"),
        [
            ("/", {"GET"}),
            ("/projects", {"GET"}),
            ("/projects/{project_id}/extract", {"POST"}),
            ("/projects/{project_id}/extract-url", {"POST"}),
        ],
        ids=["root", "projects", "extract", "extract-url"],
    )
    def test_route_exists_with_method(self, path, methods):
        """Each documented route exists and accepts exactly the expected methods."""
        matching = [r for r in router.routes if str(r.path) == path]
        assert len(matching) == 1, f"route {path} not found"
        route = matching[0]
        assert isinstance(route, APIRoute)
        assert route.methods == methods

    async def test_list_projects_returns_projects(self):
        """The /projects endpoint should return configured projects."""
        registry = ProjectRegistry()
        result = await list_projects(registry=registry)
        assert "projects" in result
        # Should have the default project from tests/projects.toml
        project_ids = [p["id"] for p in result["projects"]]
        assert "dummy" in project_ids

    async def test_extract_returns_example_metadata(self):
        """The /projects/{project_id}/extract endpoint should return example
        publication metadata."""
        registry = ProjectRegistry()
        # Use dummy backend for testing (no API calls needed)
        result = await extract(project_id="dummy", files=[], registry=registry)
        assert_dummy_metadata(result)

    async def test_extract_url_returns_example_metadata(self, monkeypatch):
        """The /projects/{project_id}/extract-url endpoint should return example
        publication metadata."""
        result, mock_fetch = await _call_extract_url(monkeypatch, "direct", DUMMY_URL)

        mock_fetch.assert_awaited_once()
        args, _ = mock_fetch.call_args
        assert args[0] == "https://example.com/paper.pdf"
        assert args[1].proxy == "direct"

        assert_dummy_metadata(result)

    def test_get_registry_returns_existing_registry(self):
        """get_registry should return the registry already on app.state."""
        expected = ProjectRegistry("tests/projects.toml")
        request = _mock_request(MagicMock(project_registry=expected))

        assert get_registry(request) is expected

    def test_get_registry_lazy_initializes_when_missing(self):
        """Lazily create and load a registry when not on app.state."""
        request = _mock_request(MagicMock(spec=[]))  # empty spec: no attrs

        result = get_registry(request)
        assert isinstance(result, ProjectRegistry)
        # Verify it was attached back to app.state
        assert request.app.state.project_registry is result
        # Verify .load() was called (projects populated from tests/projects.toml)
        assert len(result._projects) > 0

    def test_get_registry_lazy_load_fails_on_bad_config(self, monkeypatch):
        """get_registry should raise ConfigFileNotFoundError for missing config."""
        monkeypatch.setenv("BIBRA_CONFIG", "nonexistent-path/projects.toml")
        request = _mock_request(MagicMock(spec=[]))

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
        _, mock_fetch = await _call_extract_url(
            monkeypatch, "http://proxy.example.com:8080", DUMMY_URL
        )

        args, _ = mock_fetch.call_args
        assert args[1].proxy == "http://proxy.example.com:8080"

    async def test_extract_url_refused_when_proxy_not_set(self, monkeypatch):
        """With no proxy/direct configured the endpoint returns 503."""
        with pytest.raises(HTTPException) as exc_info:
            await _call_extract_url(
                monkeypatch,
                None,
                DUMMY_URL,
                side_effect=ProxyRequiredError(ProxyRequiredError.MESSAGE),
            )

        assert exc_info.value.status_code == 503
        assert "BIBRA_URL_PROXY" in exc_info.value.detail

    async def test_extract_url_policy_error_returns_400(self, monkeypatch):
        """A URL rejected by the fetch policy returns 400 with a generic detail."""
        with pytest.raises(HTTPException) as exc_info:
            await _call_extract_url(
                monkeypatch,
                "direct",
                HttpUrl("http://169.254.169.254/latest/meta-data/"),
                side_effect=UrlPolicyError("URL rejected by fetch policy"),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "URL rejected by fetch policy"
        assert "169.254.169.254" not in exc_info.value.detail

    async def test_extract_url_download_size_exceeded_returns_400(self, monkeypatch):
        """An oversized download returns 400 with a specific size detail."""
        with pytest.raises(HTTPException) as exc_info:
            await _call_extract_url(
                monkeypatch,
                "direct",
                DUMMY_URL,
                side_effect=DownloadSizeExceededError(
                    DownloadSizeExceededError.MESSAGE
                ),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == DownloadSizeExceededError.MESSAGE
        assert exc_info.value.detail != "URL rejected by fetch policy"

    async def test_extract_url_unsupported_type_returns_400(self, monkeypatch):
        """A non-PDF download returns 400 with a specific file-type detail."""
        with pytest.raises(HTTPException) as exc_info:
            await _call_extract_url(
                monkeypatch,
                "direct",
                DUMMY_URL,
                side_effect=UnsupportedContentTypeError(
                    UnsupportedContentTypeError.MESSAGE
                ),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == UnsupportedContentTypeError.MESSAGE
        assert exc_info.value.detail != "URL rejected by fetch policy"

    @pytest.mark.parametrize(
        ("side_effect", "leaked_detail"),
        [
            (
                httpx2.ConnectError("Could not resolve host"),
                "nonexistent-host",
            ),  # DNS failure
            (
                httpx2.HTTPError("connection refused to internal host"),
                "internal",
            ),  # failed download
        ],
        ids=["dns-failure-502", "http-error-502"],
    )
    async def test_extract_url_download_failure_returns_502(
        self, monkeypatch, side_effect, leaked_detail
    ):
        """A failed download returns 502 without leaking internal details."""
        with pytest.raises(HTTPException) as exc_info:
            await _call_extract_url(
                monkeypatch, "direct", DUMMY_URL, side_effect=side_effect
            )

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Failed to download URL"
        assert leaked_detail not in exc_info.value.detail

    @pytest.mark.parametrize(
        ("side_effect",),
        [
            (ProxyRequiredError(ProxyRequiredError.MESSAGE),),
            (UrlPolicyError("URL rejected by fetch policy"),),
            (DownloadSizeExceededError(DownloadSizeExceededError.MESSAGE),),
            (UnsupportedContentTypeError(UnsupportedContentTypeError.MESSAGE),),
            (httpx2.HTTPError("connection refused"),),
        ],
        ids=[
            "proxy-required-503",
            "policy-error-400",
            "size-exceeded-400",
            "unsupported-type-400",
            "http-error-502",
        ],
    )
    async def test_extract_url_error_logs_redacted_url(
        self, monkeypatch, caplog, side_effect
    ):
        """Error handlers never log userinfo/query of the submitted URL.

        A caller can plant credentials or tokens in the URL; every log
        record from the endpoint's failure paths must be free of them.
        """
        monkeypatch.setenv("BIBRA_URL_PROXY", "direct")
        url = HttpUrl(
            "https://user:supersecrettoken@api.example.com/doc.pdf?key=abc123"
        )

        with (
            patch(
                "bibra.api.v0.routes.fetch_file", new=AsyncMock(side_effect=side_effect)
            ),
            caplog.at_level("INFO"),
            pytest.raises(HTTPException),
        ):
            await extract_url(project_id="dummy", registry=ProjectRegistry(), url=url)

        assert "supersecrettoken" not in caplog.text
        assert "key=abc123" not in caplog.text
        assert "api.example.com/doc.pdf" in caplog.text

    async def test_extract_url_cleanup_temp_file_on_backend_error(self, monkeypatch):
        """The temporary file is removed even if the backend raises."""
        monkeypatch.setenv("BIBRA_URL_PROXY", "direct")

        registry = ProjectRegistry()
        mock_backend = MagicMock()
        mock_backend.extract = AsyncMock(side_effect=RuntimeError("boom"))
        # Bind the real helper so the temp-file write/cleanup runs.
        mock_backend.extract_from_bytes = BaseBackend.extract_from_bytes.__get__(
            mock_backend, type(mock_backend)
        )
        registry.get_backend = MagicMock(return_value=mock_backend)

        with (
            patch(
                "bibra.api.v0.routes.fetch_file",
                new=AsyncMock(return_value=MOCK_PDF_BYTES),
            ),
            patch("bibra.backend.base.os.unlink") as mock_unlink,
            pytest.raises(RuntimeError, match="boom"),
        ):
            await extract_url(
                project_id="dummy",
                registry=registry,
                url=DUMMY_URL,
            )

        mock_unlink.assert_called_once()
