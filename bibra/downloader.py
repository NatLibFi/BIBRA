"""HTTP file downloader with temporary storage."""

import mimetypes
import os
import tempfile
from typing import Self

import requests


class Downloader:
    """Downloads files from URLs into a temporary directory.

    Can be used as a context manager to auto-create and clean up the
    temporary directory::

        with Downloader() as dl:
            path = dl.download("https://example.com/file.pdf")

    Attributes:
        temp_dir: The root temporary directory for storing downloads.
    """

    def __init__(self, temp_dir: str | None = None) -> None:
        """Initialize the downloader.

        Args:
            temp_dir: Root directory for downloads. If ``None``, a new
                temporary directory is created when entering the context.
        """
        self._temp_dir = temp_dir
        self._temp_dir_obj: tempfile.TemporaryDirectory | None = None

    @property
    def temp_dir(self) -> str:
        """The root temporary directory for storing downloads."""
        if self._temp_dir is None:
            raise RuntimeError(
                "Downloader temp_dir not set. Use as a context manager or "
                "provide temp_dir on construction."
            )
        return self._temp_dir

    def __enter__(self) -> Self:
        if self._temp_dir is None:
            self._temp_dir_obj = tempfile.TemporaryDirectory()
            self._temp_dir = self._temp_dir_obj.name
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[override]
        if self._temp_dir_obj is not None:
            self._temp_dir_obj.cleanup()

    def download(self, url: str) -> str:
        """Download a file from *url* and return the local file path.

        The file extension is inferred from the ``Content-Type`` header
        of the HTTP response using ``mimetypes.guess_extension()``. If
        the extension cannot be determined, a ``.bin`` fallback is used.

        Args:
            url: The URL to download.

        Returns:
            Absolute path to the downloaded file inside the temp directory.

        Raises:
            requests.HTTPError: If the response indicates an error status.
            RuntimeError: If the file extension cannot be determined.
        """
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        extension = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if extension is None:
            extension = ".bin"

        filename = f"download-{id(response)}{extension}"
        filepath = os.path.join(self.temp_dir, filename)

        with open(filepath, "wb") as f:
            f.writelines(response.iter_content(chunk_size=8192))

        return filepath
