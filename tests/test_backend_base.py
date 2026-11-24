"""Tests for BaseBackend helpers: extract_from_bytes and _effective_pages."""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ConfigDict, Field

from bibra.backend.base import BaseBackend
from bibra.backend.dummy import DummyBackend
from bibra.pages import DEFAULT_PAGES
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


class _ModelConfig(BaseModel):
    """Pydantic config mimicking the LLM backends' cfg shape."""

    model_config = ConfigDict(extra="forbid")

    pages: list[int] = Field(default_factory=lambda: list(DEFAULT_PAGES))


class _ModelConfigBackend(BaseBackend[_ModelConfig]):
    """Concrete backend with a pydantic model as cfg."""

    def __init__(self, cfg: _ModelConfig) -> None:
        self.cfg = cfg

    async def extract(
        self, file_paths: list[str], pages: list[int] | None = None
    ) -> PublicationMetadata:
        return PublicationMetadata()

    @classmethod
    def build_config(cls, project) -> dict:
        return {}


def test_effective_pages_explicit_passthrough():
    """An explicit non-empty page list is returned unchanged."""
    backend = DummyBackend()

    assert backend._effective_pages([3, -1]) == [3, -1]


def test_effective_pages_none_uses_config_default():
    """None falls back to the configured default pages."""
    backend = DummyBackend()

    assert backend._effective_pages(None) == list(DEFAULT_PAGES)


def test_effective_pages_empty_raises():
    """An explicitly empty list raises ValueError."""
    backend = DummyBackend()

    with pytest.raises(ValueError, match="No pages selected for extraction"):
        backend._effective_pages([])


def test_effective_pages_none_with_empty_config_raises():
    """None with an empty configured default also raises ValueError."""
    backend = DummyBackend()
    backend.cfg["pages"] = []

    with pytest.raises(ValueError, match="No pages selected for extraction"):
        backend._effective_pages(None)


def test_effective_pages_pydantic_model_config():
    """None resolves via the model's pages field for non-dict cfg."""
    backend = _ModelConfigBackend(_ModelConfig())

    assert backend._effective_pages(None) == list(DEFAULT_PAGES)
    assert backend._effective_pages([2]) == [2]
