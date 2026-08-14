from unittest.mock import MagicMock, patch

import schemathesis

from bibra.main import app

# Load schema directly from FastAPI app
schema = schemathesis.openapi.from_asgi("/openapi.json", app)


async def _mock_aiter_bytes(*args, **kwargs):
    """Async generator that yields mock PDF content."""
    yield b"%PDF-1.4 mock content"


def _mock_httpx_response(*args, **kwargs):
    """Build a mock httpx stream response for PDF content."""
    mock_response = MagicMock()
    mock_response.headers.get.return_value = "application/pdf"
    mock_response.status_code = 200
    mock_response.aiter_bytes.return_value = _mock_aiter_bytes()
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = False
    return mock_response


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
    # Skip extract-url cases missing the required `urls` field.
    is_extract_url = (
        case.path == "/v0/projects/{project_id}/extract-url"
        and case.method.upper() == "POST"
    )
    if is_extract_url:
        body = case.body
        # Skip if `urls` is absent or empty
        has_urls = isinstance(body, dict) and bool(body.get("urls"))
        if not has_urls:
            return
        # Use dummy backend for testing to avoid real network downloads/API calls
        if (
            hasattr(case, "path")
            and case.path == "/v0/projects/{project_id}/extract-url"
        ):
            # Modify the path to use dummy project
            case.path = "/v0/projects/dummy/extract-url"

        # Mock httpx.AsyncClient stream response
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = False
            mock_response = _mock_httpx_response()
            mock_client.stream = MagicMock(return_value=mock_response)
            with patch("httpx.AsyncClient", return_value=mock_client):
                case.call_and_validate()
        return

    case.call_and_validate()
