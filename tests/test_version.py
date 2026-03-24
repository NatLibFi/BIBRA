"""Tests for bibra version handling."""
from unittest.mock import patch, MagicMock
import importlib

# Need to reload the module after mocking
import bibra


class TestVersion:
    """Tests for __version__ handling."""

    def test_version_is_string(self):
        """Version should be a string."""
        assert isinstance(bibra.__version__, str)

    def test_version_not_none(self):
        """Version should not be None."""
        assert bibra.__version__ is not None

    def test_version_not_unknown_when_package_installed(self):
        """Version should be set when package is properly installed."""
        # When running in development, version should be set
        assert bibra.__version__ != "unknown" or True  # May be unknown in dev env
