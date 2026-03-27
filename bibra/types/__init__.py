from pydantic import BaseModel
from typing import List, Optional


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
