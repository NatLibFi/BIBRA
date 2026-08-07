"""API routes for BIBRA."""

import logging
import os
import tempfile
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from bibra import __version__
from bibra.config import ProjectRegistry
from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)

router = APIRouter()
registry = ProjectRegistry(os.environ.get("BIBRA_CONFIG"))


@router.get("/")
async def root():
    """Return the API version information."""
    return {"version": __version__, "message": "Welcome to BIBRA API v0"}


@router.get("/projects")
async def list_projects():
    """Return a list of configured projects."""
    return {"projects": registry.list_projects()}


class ExtractRequest(BaseModel):
    """Request model for extract endpoint."""

    files: list[UploadFile]


@router.post(
    "/projects/{project_id}/extract",
    responses={400: {"description": "Bad Request - malformed multipart data"}},
)
async def extract(
    project_id: str,
    files: Annotated[list[UploadFile], File(...)],
) -> PublicationMetadata:
    """
    Extract publication metadata from PDF or image files for a specific project.

    Args:
        project_id: The ID of the project to extract metadata for
        files: List of PDF or image files to process

    Returns:
        PublicationMetadata: Extracted metadata as JSON
    """
    temp_files: list[str] = []
    try:
        for upload_file in files:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                temp_files.append(tmp.name)
                while chunk := await upload_file.read(1024 * 1024):
                    tmp.write(chunk)

        # Get backend for the project
        try:
            backend = registry.get_backend(project_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        # Extract metadata using the backend
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
