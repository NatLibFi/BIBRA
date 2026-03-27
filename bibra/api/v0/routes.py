from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from bibra.backend.dummy import DummyBackend
from bibra.models import PublicationMetadata

router = APIRouter()



class ExtractRequest(BaseModel):
    """Request model for extract endpoint."""

    files: List[UploadFile]
    text: Optional[str] = None


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


@router.post("/projects/{project_id}/extract")
async def extract(
    project_id: str,
    files: List[UploadFile] = File(...),
    text: Optional[str] = Form(None),
) -> PublicationMetadata:
    """
    Extract publication metadata from PDF or image files for a specific project.

    Args:
        project_id: The ID of the project to extract metadata for
        files: List of PDF or image files to process
        text: Optional additional text context

    Returns:
        PublicationMetadata: Extracted metadata as JSON
    """

    # Create dummybackend instance
    backend = DummyBackend()
    # Call backend to extract metadata
    return backend.extract(files, text)
