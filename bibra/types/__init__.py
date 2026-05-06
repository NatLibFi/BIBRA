from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


class PublicationMetadata(BaseModel):
    """Response model for publication metadata extraction."""

    model_config = ConfigDict(populate_by_name=True)

    language: Optional[str] = None
    title: Optional[str] = None
    alt_title: Optional[str] = None
    creator: List[str] = []
    year: Optional[str] = None
    publisher: List[str] = []
    doi: Optional[str] = None
    e_isbn: List[str] = Field(default=[], alias="e-isbn")
    p_isbn: List[str] = Field(default=[], alias="p-isbn")
    e_issn: Optional[str] = None
    p_issn: Optional[str] = None
    type_coar: Optional[str] = None
