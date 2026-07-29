from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("bibra")
except PackageNotFoundError:
    __version__ = "unknown"
