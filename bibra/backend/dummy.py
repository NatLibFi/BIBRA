"""Dummy backend for testing."""

from typing import Any

from bibra.backend.base import BaseBackend
from bibra.pages import DEFAULT_PAGES
from bibra.types import PublicationMetadata


class DummyBackend(BaseBackend[dict[str, Any]]):
    """Dummy backend implementation for testing."""

    cfg: dict[str, Any]

    def __init__(self) -> None:
        """Initialize the dummy backend."""
        self.cfg: dict[str, Any] = {"pages": list(DEFAULT_PAGES)}

    @classmethod
    def build_config(cls, project: Any) -> dict[str, Any]:
        """Build constructor kwargs from a ProjectConfig."""
        return {}

    async def extract(
        self, file_paths: list[str], pages: list[int] | None = None
    ) -> PublicationMetadata:
        """Extract publication metadata from files.

        Raises:
            ValueError: If the effective page selection is empty
                (i.e. the caller explicitly passed pages=[]).
        """
        effective_pages = pages if pages is not None else self.cfg["pages"]
        if not effective_pages:
            raise ValueError("No pages selected for extraction")

        return PublicationMetadata(
            language="en",
            title="Machine Learning Approaches for Software Defect Prediction",
            creator=["Smith, John", "Johnson, Emily"],
            year="2023",
            publisher=["Springer", "ACM"],
            doi="10.1234/example.doi.12345",
            e_isbn=["978-0-123456-78-9"],
            type_coar="article",
        )
