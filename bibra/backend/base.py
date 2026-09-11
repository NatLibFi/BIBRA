"""Abstract base class for all backends."""

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from typing import Any

from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)


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

    async def extract_from_bytes(self, data: bytes) -> PublicationMetadata:
        """Extract publication metadata from in-memory PDF bytes.

        Writes the bytes to a temporary ``.pdf`` file and calls
        :meth:`extract` with it. The temporary file is removed afterwards,
        even if extraction fails.

        Args:
            data: The PDF file contents.

        Returns:
            PublicationMetadata: Extracted metadata.
        """
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(data)
            return await self.extract([tmp_path])
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    logger.debug(
                        "Failed to remove temporary file: %s",
                        tmp_path,
                        exc_info=True,
                    )

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
