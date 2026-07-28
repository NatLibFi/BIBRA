from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PublicationMetadata(BaseModel):
    """Response model for publication metadata extraction."""

    model_config = ConfigDict(populate_by_name=True)

    language: str | None = None
    title: str | None = None
    alt_title: str | None = None
    creator: list[str] = []
    year: str | None = None
    publisher: list[str] = []
    doi: str | None = None
    e_isbn: list[str] = Field(default=[], alias="e-isbn")
    p_isbn: list[str] = Field(default=[], alias="p-isbn")
    e_issn: str | None = Field(default=None, alias="e-issn")
    p_issn: str | None = Field(default=None, alias="p-issn")
    type_coar: str | None = None
