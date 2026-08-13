"""Abstract base class for all backends."""

from abc import ABC, abstractmethod
from typing import Any

from bibra.types import PublicationMetadata


class BaseBackend(ABC):
    """Abstract base class for all backend implementations.

    Every backend must implement the `extract` method to process files
    and return publication metadata, and `build_config` to construct
    its configuration from a generic ProjectConfig.
    """

    @abstractmethod
    async def extract(self, file_paths: list[str]) -> PublicationMetadata:
        """Extract publication metadata from files.

        Args:
            file_paths: List of file paths to process.

        Returns:
            PublicationMetadata: Extracted metadata.
        """

    @classmethod
    @abstractmethod
    def build_config(cls, project: Any) -> dict[str, Any]:
        """Build constructor kwargs from a ProjectConfig.

        Args:
            project: ProjectConfig with id, name, backend, endpoint,
                api_key, and extra dict of backend-specific options.

        Returns:
            Dict of kwargs suitable for backend constructors.
        """
