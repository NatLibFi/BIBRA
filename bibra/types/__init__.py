from pydantic import BaseModel, ConfigDict, Field


class Version(BaseModel):
    """Response model for the root endpoint."""

    version: str = Field(
        ..., description="Current BIBRA version string", examples=["0.1.0"]
    )
    message: str = Field(
        ..., description="Welcome message", examples=["Welcome to BIBRA API v0"]
    )


class ProjectInfo(BaseModel):
    """Summary information for a single configured project."""

    id: str = Field(..., description="Project identifier", examples=["my_project"])
    name: str = Field(
        ..., description="Human-readable project name", examples=["My Project"]
    )
    description: str = Field(
        ...,
        description="Short description of the project",
        examples=["Project using dummy backend"],
    )


class Projects(BaseModel):
    """Response model for the list-projects endpoint."""

    projects: list[ProjectInfo] = Field(..., description="List of configured projects")


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
