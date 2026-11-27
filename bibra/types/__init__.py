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


class MarcField(BaseModel):
    """A single MARC data field with subfields and optional indicators."""

    subfields: list[dict[str, str]] = Field(
        default_factory=list,
        description="Ordered list of subfields, e.g. [{'a': 'Title text'}]",
        examples=[
            [
                {"a": "Machine Learning Approaches"},
                {"b": "a subtitle"},
            ]
        ],
    )
    ind1: str | None = Field(
        default=None,
        description="First indicator (single character)",
        examples=["0"],
    )
    ind2: str | None = Field(
        default=None,
        description="Second indicator (single character)",
        examples=[" "],
    )


class MarcRecord(BaseModel):
    """MARC21 record; each field maps its 3-digit tag to a :class:`MarcField`
    (data fields) or a plain string (control fields)."""

    fields: list[dict[str, MarcField | str]] = Field(
        default_factory=list,
        description=(
            "MARC fields, each keyed by its 3-digit tag; data fields map to "
            "a MarcField, control fields map to their string value"
        ),
        examples=[
            [
                {
                    "245": {
                        "subfields": [{"a": "Machine Learning Approaches"}],
                        "ind1": "0",
                        "ind2": " ",
                    }
                }
            ]
        ],
    )


class PublicationMetadata(BaseModel):
    """Response model for publication metadata extraction."""

    model_config = ConfigDict(populate_by_name=True)

    language: str | None = None
    title: str | None = None
    alt_title: list[str] = []
    creator: list[str] = []
    year: str | None = None
    publisher: list[str] = []
    doi: str | None = None
    e_isbn: list[str] = Field(default=[], alias="e-isbn")
    p_isbn: list[str] = Field(default=[], alias="p-isbn")
    e_issn: str | None = Field(default=None, alias="e-issn")
    p_issn: str | None = Field(default=None, alias="p-issn")
    type_coar: str | None = None
