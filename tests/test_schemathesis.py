"""Schemathesis property-based tests for the API (no real network calls)."""

from unittest.mock import AsyncMock, patch

import schemathesis

from bibra.main import app

# Load schema directly from FastAPI app
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

# POST endpoints that need the dummy project to avoid real API calls,
# keyed by the form field that must be present for the case to be valid.
_DUMMY_PROJECT_ENDPOINTS = {
    "/v0/projects/{project_id}/extract": (
        "/v0/projects/dummy/extract",
        "files",
    ),
    "/v0/projects/{project_id}/extract-url": (
        "/v0/projects/dummy/extract-url",
        "url",
    ),
}


def _prepare(case) -> bool:
    """Rewrite the project id to "dummy"; return False if the case is invalid."""
    if case.method.upper() != "POST":
        return True
    rewrite = _DUMMY_PROJECT_ENDPOINTS.get(case.path)
    if rewrite is None:
        return True
    dummy_path, required_field = rewrite
    # Skip bodies missing the required field.
    if not (isinstance(case.body, dict) and case.body.get(required_field)):
        return False
    case.path = dummy_path
    return True


@schema.parametrize()
def test_api(case):
    if not _prepare(case):
        return
    if case.path == "/v0/projects/dummy/extract-url":
        # Mock the hardened fetch layer so no network activity occurs. The
        # SSRF validation logic itself is covered by dedicated tests in
        # tests/test_net_security.py and tests/test_net_security_fetch.py.
        with patch(
            "bibra.api.v0.routes.fetch_file",
            new=AsyncMock(return_value=b"%PDF-1.4 mock content"),
        ):
            case.call_and_validate()
        return
    case.call_and_validate()
