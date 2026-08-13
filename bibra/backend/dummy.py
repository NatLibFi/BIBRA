"""Dummy backend for testing."""

from typing import Any

from bibra.backend.base import BaseBackend
from bibra.types import PublicationMetadata


class DummyBackend(BaseBackend):
    """Dummy backend implementation for testing."""

    @classmethod
    def build_config(cls, project: Any) -> dict[str, Any]:
        """Build constructor kwargs from a ProjectConfig."""
        return {}

    async def extract(self, file_paths: list[str]) -> PublicationMetadata:
        """Extract publication metadata from files."""
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
