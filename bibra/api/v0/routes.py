"""API routes for BIBRA."""

import logging
import os
import tempfile
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import HttpUrl

from bibra import __version__
from bibra.config import (
    ConfigError,
    ProjectNotFoundError,
    ProjectRegistry,
    load_url_fetch_policy,
)
from bibra.net_security import ProxyRequiredError, UrlPolicyError, fetch_file
from bibra.types import Projects, PublicationMetadata, Version

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


@router.get(
    "/", response_model=Version, summary="Get version information", tags=["General"]
)
async def root():
    """Return version information of BIBRA and the API."""
    return {"version": __version__, "message": "Welcome to BIBRA API v0"}


@router.get(
    "/projects", response_model=Projects, summary="List projects", tags=["Projects"]
)
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
    summary="Extract metadata",
    tags=["Extraction"],
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

    Example:
        ```
        curl -X POST "http://localhost:8000/v0/projects/my_project/extract" \
             -F "files=@/path/to/document.pdf"
        ```
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


@router.post(
    "/projects/{project_id}/extract-url",
    responses={
        400: {"description": "Bad Request - URL or content violates the fetch policy"},
        502: {"description": "Bad Gateway - download failed"},
        503: {"description": "Service Unavailable - URL fetching is not configured"},
    },
)
async def extract_url(
    project_id: str,
    registry: Annotated[ProjectRegistry, Depends(get_registry)],
    url: HttpUrl = Form(...),  # noqa: B008
) -> PublicationMetadata:
    """
    Extract publication metadata from a PDF file at a given URL for a
    specific project.

    The download is performed with the SSRF-hardened fetch layer
    (``bibra.net_security``): egress is only allowed through a configured
    proxy or in explicit direct mode, the URL and every redirect hop are
    validated against the fetch policy, and the downloaded bytes are
    verified before being handed to the backend.

    Args:
        project_id: The ID of the project to extract metadata for
        url: URL pointing to a file to process

    Returns:
        PublicationMetadata: Extracted metadata as JSON

    Raises:
        HTTPException: 400 if the URL or content violates the fetch policy,
            404 if the project is unknown, 502 if the download fails,
            503 if URL fetching is disabled (no proxy/direct configured).
    """
    try:
        backend = registry.get_backend(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConfigError as e:
        logger.exception("Configuration error")
        raise HTTPException(status_code=500, detail=str(e))

    url_str = str(url)
    policy = load_url_fetch_policy()

    try:
        data = await fetch_file(url_str, policy)
    except ProxyRequiredError as e:
        logger.info("URL fetch refused (no proxy configured): %s", url_str)
        raise HTTPException(status_code=503, detail=e.MESSAGE)
    except UrlPolicyError as e:
        # Client-facing message stays generic; details were logged by
        # the fetch layer.
        logger.info("URL rejected by fetch policy: %s", url_str)
        raise HTTPException(status_code=400, detail=str(e))
    except httpx2.HTTPError:
        logger.exception("HTTP Error downloading %s", url_str)
        raise HTTPException(status_code=502, detail="Failed to download URL")

    return await backend.extract_from_bytes(data)
