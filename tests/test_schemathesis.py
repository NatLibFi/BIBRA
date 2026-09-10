import schemathesis

from bibra.main import app

# Load schema directly from FastAPI app
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

# Minimal placeholder PDF bytes; the dummy backend ignores file contents.
_DUMMY_PDF = b"%PDF-1.4 dummy test document"


@schema.parametrize()
def test_api(case):
    # The extract endpoint expects multipart file uploads, but Schemathesis
    # generates form fields as plain strings, which FastAPI rejects with 422.
    # Override the body with raw bytes so Schemathesis sends a real file part.
    is_extract = (
        case.path == "/v0/projects/{project_id}/extract"
        and case.method.upper() == "POST"
    )
    if is_extract:
        # Use the dummy project so no real backend API calls are made.
        case.path = "/v0/projects/dummy/extract"
        case.body = {"files": [_DUMMY_PDF]}
    case.call_and_validate()
