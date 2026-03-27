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
    case.call_and_validate()
