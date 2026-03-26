from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

router = APIRouter()


# Pydantic models for request/response validation
class PublicationMetadata(BaseModel):
    """Response model for publication metadata extraction."""
    language: Optional[str] = None
    title: Optional[str] = None
    alt_title: Optional[str] = None
    creator: List[str] = []
    year: Optional[str] = None
    publisher: List[str] = []
    doi: Optional[str] = None
    e_isbn: List[str] = []
    p_isbn: List[str] = []
    e_issn: Optional[str] = None
    p_issn: Optional[str] = None
    type_coar: Optional[str] = None


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
        "status": "active"
    },
    {
        "id": "project-002",
        "name": "Example Project Beta",
        "description": "Another example project with different configuration",
        "created_at": "2024-02-20T14:30:00Z",
        "status": "active"
    },
    {
        "id": "project-003",
        "name": "Example Project Gamma",
        "description": "A third example project",
        "created_at": "2024-03-10T09:15:00Z",
        "status": "inactive"
    }
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
    text: Optional[str] = Form(None)
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
    # Mockup implementation - always returns example data
    # In a real implementation, this would call an OCR/PDF extraction service
    
    example_metadata = PublicationMetadata(
        language="en",
        title="Machine Learning Approaches for Software Defect Prediction",
        creator=["Smith, John", "Johnson, Emily"],
        year="2023",
        publisher=["Springer", "ACM"],
        doi="10.1234/example.doi.12345",
        e_isbn=["978-0-123456-78-9"],
        type_coar="article"
    )
    
    return example_metadata
