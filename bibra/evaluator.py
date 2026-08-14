"""Evaluation pipeline for metadata extraction results."""

import asyncio
import json
from typing import Any

from bibra.backend.base import BaseBackend
from bibra.downloader import Downloader


def load_ground_truth(file_paths: list[str]) -> list[dict[str, Any]]:
    """Load ground truth records from one or more JSONL files.

    Each line is parsed as JSON and returned as-is. The caller is
    responsible for accessing the keys it needs (e.g. ``url``,
    ``ground_truth``).

    Args:
        file_paths: Paths to JSONL files.

    Returns:
        List of ground truth record dictionaries.
    """
    records: list[dict[str, Any]] = []
    for path in file_paths:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def run_evaluation(
    backend: BaseBackend, records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Run extraction against each record and compare with ground truth.

    For each record the PDF at ``record["url"]`` is downloaded, metadata
    is extracted using *backend*, and the result is collected alongside
    the original ground truth. The actual comparison logic is a stub.

    Args:
        backend: Configured backend instance for extraction.
        records: Ground truth records loaded from JSONL files.

    Returns:
        List of result dictionaries, one per record, containing
        ``url``, ``ground_truth``, ``extracted``, and ``match``.
    """
    results: list[dict[str, Any]] = []

    with Downloader() as downloader:
        for record in records:
            url = record.get("url")
            if url is None:
                continue

            filepath = downloader.download(url)
            extracted = asyncio.run(backend.extract([filepath]))

            results.append(
                {
                    "url": url,
                    "ground_truth": record.get("ground_truth"),
                    "extracted": extracted.model_dump(),
                    "match": None,  # stub
                }
            )

    return results
