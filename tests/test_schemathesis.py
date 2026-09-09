from unittest.mock import AsyncMock, patch

import schemathesis

from bibra.main import app

# Load schema directly from FastAPI app
schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@schema.parametrize()
def test_api(case):
    # Skip extract cases missing the required `files` field.
    is_extract = (
        case.path == "/v0/projects/{project_id}/extract"
        and case.method.upper() == "POST"
    )
    if is_extract:
        body = case.body
        # Skip if `files` is absent or empty
        has_files = isinstance(body, dict) and bool(body.get("files"))
        if not has_files:
            return
        # Use dummy backend for testing to avoid real API calls
        if hasattr(case, "path") and case.path == "/v0/projects/{project_id}/extract":
            # Modify the path to use dummy project
            case.path = "/v0/projects/dummy/extract"
    # Skip extract-url cases missing the required `url` field.
    is_extract_url = (
        case.path == "/v0/projects/{project_id}/extract-url"
        and case.method.upper() == "POST"
    )
    if is_extract_url:
        body = case.body
        # Skip if `url` is absent or empty
        has_url = isinstance(body, dict) and bool(body.get("url"))
        if not has_url:
            return
        # Use dummy backend for testing to avoid real network downloads/API
        # calls
        if (
            hasattr(case, "path")
            and case.path == "/v0/projects/{project_id}/extract-url"
        ):
            # Modify the path to use dummy project
            case.path = "/v0/projects/dummy/extract-url"

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
