import logging
import tempfile
import os

from bibra import __version__

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from typing import List, Dict, Any

from bibra.backend.dummy import DummyBackend
from bibra.backend.greylitlm import GreyLitLMBackend
from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)

router = APIRouter()


class ExtractRequest(BaseModel):
    """Request model for extract endpoint."""

    files: List[UploadFile]


# Example project data - can be extended as needed
PROJECTS: List[Dict[str, Any]] = [
    {
        "id": "greylitlm",
        "name": "GreyLitLM Backend",
        "description": "Testing project using the GreyLitLM backend",
        "created_at": "2024-01-15T10:00:00Z",
        "status": "active",
    },
    {
        "id": "dummy",
        "name": "Dummy Backend",
        "description": "Testing project using the dummy backend",
        "created_at": "2024-01-15T10:00:00Z",
        "status": "active",
    },
]


@router.get("/")
async def root():
    """Return the API version information."""
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
    # Save uploaded files to temporary paths for backend processing
    temp_files: List[str] = []
    try:
        for upload_file in files:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                content = await upload_file.read()
                tmp.write(content)
                temp_files.append(tmp.name)

        # Choose backend based on project_id
        if project_id == "dummy":
            # Use dummy backend for testing
            backend = DummyBackend()
            result = backend.extract(temp_files)
        else:
            # Use greylitlm backend for real extraction
            backend = GreyLitLMBackend()
            result = await backend.extract(temp_files)
        return result
    finally:
        # Clean up all temporary files
        for tmp_path in temp_files:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.debug(
                    "Failed to remove temporary file: %s", tmp_path, exc_info=True
                )
