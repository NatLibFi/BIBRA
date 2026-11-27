"""Abstract base class for all backends."""

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from typing import Any

from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)


class BaseBackend[T](ABC):
    """Abstract base class for all backend implementations.

    Every backend must implement the `extract` method to process files
    and return publication metadata, and `build_config` to construct
    its configuration from a generic ProjectConfig.
    """

    cfg: T

    @abstractmethod
    async def extract(
        self, file_paths: list[str], pages: list[int] | None = None
    ) -> PublicationMetadata:
        """Extract publication metadata from files.

        Args:
            file_paths: List of file paths to process.
            pages: Optional 1-based page numbers to extract (negative
                counts from the last page). If None, the backend's
                configured default pages are used.

        Raises:
            ValueError: If the effective page selection is empty.

        Returns:
            PublicationMetadata: Extracted metadata.
        """

    def _effective_pages(self, pages: list[int] | None) -> list[int]:
        """Resolve the page selection to use for extraction.

        Args:
            pages: Explicit 1-based page numbers (negative counts from
                the last page). If None, the backend's configured default
                pages are used.

        Returns:
            The non-empty page list to use for extraction.

        Raises:
            ValueError: If the resolved page selection is empty.
        """
        if pages is None:
            if isinstance(self.cfg, dict):
                pages = self.cfg.get("pages") or []
            else:
                pages = getattr(self.cfg, "pages", [])
        if not pages:
            raise ValueError("No pages selected for extraction")
        return pages

    async def extract_from_bytes(
        self, data: bytes, pages: list[int] | None = None
    ) -> PublicationMetadata:
        """Extract publication metadata from in-memory PDF bytes.

        Writes the bytes to a temporary ``.pdf`` file and calls
        :meth:`extract` with it. The temporary file is removed afterwards,
        even if extraction fails.

        Args:
            data: The PDF file contents.
            pages: Optional 1-based page numbers to extract; passed to
                :meth:`extract`.

        Raises:
            ValueError: If the effective page selection is empty.

        Returns:
            PublicationMetadata: Extracted metadata.
        """
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(data)
            return await self.extract([tmp_path], pages=pages)
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
