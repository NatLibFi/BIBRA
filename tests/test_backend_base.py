"""Tests for the BaseBackend.extract_from_bytes helper."""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bibra.backend.base import BaseBackend
from bibra.types import PublicationMetadata


class _ConcreteBackend(BaseBackend):
    """Minimal concrete backend for exercising the shared helper.

    Records the file paths it is given so tests can assert the temp file
    held the right bytes and was removed afterwards.
    """

    def __init__(self, holder: list[str], expected: bytes | None = None):
        self._holder = holder
        self._expected = expected

    async def extract(
        self, file_paths: list[str], pages: list[int] | None = None
    ) -> PublicationMetadata:
        self._holder.extend(file_paths)
        # Verify the temp file held exactly the bytes the helper wrote.
        # (to_thread keeps the async method free of blocking I/O.)
        if self._expected is not None:
            for path in file_paths:
                contents = await asyncio.to_thread(Path(path).read_bytes)
                if contents != self._expected:
                    raise AssertionError("temp file contents mismatch")
        return PublicationMetadata()

    @classmethod
    def build_config(cls, project) -> dict:
        return {}


def test_writes_bytes_and_cleans_up():
    """The temp file is created with the exact bytes and removed after."""
    holder: list[str] = []
    backend = _ConcreteBackend(holder, expected=b"%PDF-1.4 test")

    with patch("bibra.backend.base.os.unlink") as mock_unlink:
        result = asyncio.run(backend.extract_from_bytes(b"%PDF-1.4 test"))

    assert isinstance(result, PublicationMetadata)
    # extract() was called with exactly one temp file path.
    assert len(holder) == 1
    (tmp_path,) = holder
    assert tmp_path.endswith(".pdf")
    # The helper removed the temp file.
    mock_unlink.assert_called_once_with(tmp_path)


def test_temp_file_removed_even_on_error():
    """The temp file is removed even when extract() raises."""

    class FailingBackend(_ConcreteBackend):
        async def extract(
            self, file_paths: list[str], pages: list[int] | None = None
        ) -> PublicationMetadata:
            self._holder.extend(file_paths)
            raise RuntimeError("boom")

    holder: list[str] = []
    backend = FailingBackend(holder)

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(backend.extract_from_bytes(b"%PDF-1.4 test"))

    assert len(holder) == 1
    # The real unlink runs (no patch): the file is gone from disk.
    assert not os.path.exists(holder[0])


def test_pages_passed_to_extract():
    """Pages given to extract_from_bytes reach extract unchanged."""
    holder: list[str] = []
    backend = RecordingPagesBackend(holder)

    asyncio.run(backend.extract_from_bytes(b"%PDF-1.4 test", pages=[1, -1]))

    assert backend.pages == [1, -1]


def test_pages_default_none():
    """extract_from_bytes without pages passes None to extract."""
    holder: list[str] = []
    backend = RecordingPagesBackend(holder)

    asyncio.run(backend.extract_from_bytes(b"%PDF-1.4 test"))

    assert backend.pages is None


class RecordingPagesBackend(_ConcreteBackend):
    """Concrete backend that records the pages it is given."""

    def __init__(self, holder: list[str]):
        super().__init__(holder)
        self.pages: list[int] | None = None

    async def extract(
        self, file_paths: list[str], pages: list[int] | None = None
    ) -> PublicationMetadata:
        self.pages = pages
        return await super().extract(file_paths, pages=pages)
