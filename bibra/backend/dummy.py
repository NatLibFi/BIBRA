from typing import List, Optional

from bibra.types import PublicationMetadata


class DummyBackend:
    """Dummy backend implementation for testing."""

    def extract(self, files: List, text: Optional[str] = None) -> PublicationMetadata:
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
