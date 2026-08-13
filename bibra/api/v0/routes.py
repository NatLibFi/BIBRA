"""API routes for BIBRA."""

import logging
import os
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from bibra import __version__
from bibra.config import ConfigError, ProjectNotFoundError, ProjectRegistry
from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)

router = APIRouter()


def get_registry(request: Request) -> ProjectRegistry:
    """FastAPI dependency that returns the project registry from app state.

    Lazily initializes the registry if startup hooks were skipped
    (e.g. in unit tests or scripts that bypass ASGI lifespan).
    """
    registry = getattr(request.app.state, "project_registry", None)
    if registry is None:
        registry = ProjectRegistry(os.environ.get("BIBRA_CONFIG"))
        registry.load()
        request.app.state.project_registry = registry
    return registry


@router.get("/")
async def root():
    """Return the API version information."""
    return {"version": __version__, "message": "Welcome to BIBRA API v0"}


@router.get("/projects")
async def list_projects(registry: Annotated[ProjectRegistry, Depends(get_registry)]):
    """Return a list of configured projects."""
    try:
        projects = registry.list_projects()
    except ConfigError as e:
        logger.exception("Configuration error")
        raise HTTPException(status_code=500, detail=str(e))
    return {"projects": projects}


@router.post(
    "/projects/{project_id}/extract",
    responses={400: {"description": "Bad Request - malformed multipart data"}},
)
async def extract(
    project_id: str,
    files: Annotated[list[UploadFile], File(...)],
    registry: Annotated[ProjectRegistry, Depends(get_registry)],
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
        except ProjectNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ConfigError as e:
            logger.exception("Configuration error")
            raise HTTPException(status_code=500, detail=str(e))
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
