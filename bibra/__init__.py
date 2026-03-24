from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("bibra")
except PackageNotFoundError:
    __version__ = "unknown"
