"""Tests for the DummyBackend page selection contract."""

import asyncio

import pytest

from bibra.backend.dummy import DummyBackend


class TestDummyBackendPages:
    """DummyBackend must follow the shared empty-selection contract."""

    def test_extract_returns_metadata_by_default(self):
        """Without a pages argument, the configured default pages are used."""
        backend = DummyBackend()
        result = asyncio.run(backend.extract(["dummy.pdf"]))
        assert result.title is not None

    def test_extract_with_pages(self):
        """An explicit non-empty page selection works."""
        backend = DummyBackend()
        result = asyncio.run(backend.extract(["dummy.pdf"], pages=[1, -1]))
        assert result.title is not None

    def test_extract_raises_on_empty_selection(self):
        """Explicitly empty pages must raise ValueError, per the base contract."""
        backend = DummyBackend()
        with pytest.raises(ValueError, match="No pages selected"):
            asyncio.run(backend.extract(["dummy.pdf"], pages=[]))

    def test_default_pages_configured(self):
        """The dummy backend's configured pages default to DEFAULT_PAGES."""
        from bibra.pages import DEFAULT_PAGES

        assert DummyBackend().cfg["pages"] == DEFAULT_PAGES
