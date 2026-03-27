from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from typing import List, Dict, Any

from bibra.backend.dummy import DummyBackend
from bibra.backend.greylitlm import GreylitLMBackend
from bibra.types import PublicationMetadata

router = APIRouter()


class ExtractRequest(BaseModel):
    """Request model for extract endpoint."""

    files: List[UploadFile]


# Example project data - can be extended as needed
PROJECTS: List[Dict[str, Any]] = [
    {
        "id": "project-001",
        "name": "Example Project Alpha",
        "description": "This is an example project for testing the API",
        "created_at": "2024-01-15T10:00:00Z",
        "status": "active",
    },
    {
        "id": "project-002",
        "name": "Example Project Beta",
        "description": "Another example project with different configuration",
        "created_at": "2024-02-20T14:30:00Z",
        "status": "active",
    },
    {
        "id": "project-003",
        "name": "Example Project Gamma",
        "description": "A third example project",
        "created_at": "2024-03-10T09:15:00Z",
        "status": "inactive",
    },
]


@router.get("/")
async def root():
    """Return the API version information."""
    from bibra import __version__

    return {"version": __version__, "message": "Welcome to BIBRA API v0"}


@router.get("/projects")
async def list_projects():
    """Return a list of available projects."""
    return {"projects": PROJECTS}


@router.post(
    "/projects/{project_id}/extract",
    responses={400: {"description": "Bad Request - malformed multipart data"}},
)
async def extract(
    project_id: str,
    files: List[UploadFile] = File(...),
) -> PublicationMetadata:
    """
    Extract publication metadata from PDF or image files for a specific project.

    Args:
        project_id: The ID of the project to extract metadata for
        files: List of PDF or image files to process

    Returns:
        PublicationMetadata: Extracted metadata as JSON
    """

    # Choose backend based on project_id
    if project_id == "dummy":
        # Use dummy backend for testing
        backend = DummyBackend()
        result = backend.extract(files)
    else:
        # Use greylitlm backend for real extraction
        backend = GreylitLMBackend()
        result = await backend.extract(files)
    return result
