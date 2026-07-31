"""Abstract base class for all backends."""

from abc import ABC, abstractmethod

from bibra.types import PublicationMetadata


class BaseBackend(ABC):
    """Abstract base class for all backend implementations.

    Every backend must implement the `extract` method to process files
    and return publication metadata.
    """

    @abstractmethod
    async def extract(self, file_paths: list[str]) -> PublicationMetadata:
        """Extract publication metadata from files.

        Args:
            file_paths: List of file paths to process.

        Returns:
            PublicationMetadata: Extracted metadata.
        """
