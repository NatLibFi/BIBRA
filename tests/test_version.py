"""Tests for bibra version handling."""

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
        from importlib.metadata import PackageNotFoundError, version

        try:
            version("bibra")
            # Package is installed, version should not be "unknown"
            assert bibra.__version__ != "unknown"
        except PackageNotFoundError:
            # Development install, version is expected to be "unknown"
            assert bibra.__version__ == "unknown"
