"""Evaluation pipeline for metadata extraction results."""

import asyncio
import json
from typing import Any

import Levenshtein

from bibra.backend.base import BaseBackend
from bibra.downloader import Downloader
from bibra.types import PublicationMetadata

# Levenshtein similarity threshold to consider a fuzzy match "correct".
FUZZY_MATCH_THRESHOLD = 0.95


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


# ---------------------------------------------------------------------------
# Field-level comparison helpers
# ---------------------------------------------------------------------------


def _compare_simple_string(true_val: Any, pred_val: Any) -> tuple[str, float]:
    """Compare two scalar string values.

    Returns:
        Tuple of (match_type, score).
    """
    if pred_val is None and true_val is None:
        return ("not-relevant", 1)
    if true_val is None:
        return ("found-nonexistent", 0)
    if pred_val is None:
        return ("not-found", 0)
    if true_val == pred_val:
        return ("exact", 1)
    return ("wrong", 0)


def _compare_fuzzy_string(true_val: Any, pred_val: Any) -> tuple[str, float]:
    """Compare two strings with fuzzy (Levenshtein) matching.

    Returns:
        Tuple of (match_type, score).
    """
    base_result = _compare_simple_string(true_val, pred_val)
    if base_result[0] != "wrong":
        return base_result

    if true_val.lower() == pred_val.lower():
        return ("case", 1)
    if Levenshtein.ratio(true_val, pred_val) >= FUZZY_MATCH_THRESHOLD:
        return ("almost", 1)
    if Levenshtein.ratio(true_val.lower(), pred_val.lower()) >= FUZZY_MATCH_THRESHOLD:
        return ("almost-case", 1)
    return ("wrong", 0)


def _compare_set(true_val: Any, pred_val: Any) -> tuple[str, float]:
    """Compare two list/set values using F1 score.

    Returns:
        Tuple of (match_type, score).
    """
    true_set = set(true_val) if true_val else set()
    pred_set = set(pred_val) if pred_val else set()

    if not true_set and not pred_set:
        return ("not-relevant", 1)
    if not true_set:
        return ("found-nonexistent", 0)
    if not pred_set:
        return ("not-found", 0)
    if true_set == pred_set:
        return ("exact", 1)

    # Calculate F1 score.
    true_positives = len(true_set & pred_set)
    false_positives = len(pred_set - true_set)
    false_negatives = len(true_set - pred_set)

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0
    )
    f1 = (
        2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    )

    if true_set.issubset(pred_set):
        return ("superset", f1)
    if true_set.issuperset(pred_set):
        return ("subset", f1)
    if true_set & pred_set:
        return ("overlap", f1)
    return ("wrong", 0)


def _compare_e_issn(true_val: Any, pred_val: Any, p_issn_val: Any) -> tuple[str, float]:
    """Compare e_issn with special handling for printed ISSN confusion.

    Returns:
        Tuple of (match_type, score).
    """
    base_result = _compare_simple_string(true_val, pred_val)
    if base_result[0] != "wrong":
        return base_result

    # Check whether the predicted ISSN is actually the printed ISSN.
    if p_issn_val and pred_val == p_issn_val:
        if true_val:
            return ("printed-issn", 0)
        else:
            return ("printed-issn", 1)

    return ("wrong", 0)


# ---------------------------------------------------------------------------
# Per-record evaluation
# ---------------------------------------------------------------------------


def _compare_field(
    field: str,
    gt: PublicationMetadata,
    pred: PublicationMetadata,
) -> tuple[str, float]:
    """Compare a single field between ground truth and prediction.

    Returns:
        Tuple of (match_type, score).
    """
    if field == "language":
        return _compare_simple_string(gt.language, pred.language)

    if field == "title":
        return _compare_fuzzy_string(gt.title, pred.title)

    if field == "alt_title":
        return _compare_fuzzy_string(gt.alt_title, pred.alt_title)

    if field == "creator":
        return _compare_set(gt.creator, pred.creator)

    if field == "year":
        return _compare_simple_string(gt.year, pred.year)

    if field == "publisher":
        return _compare_set(gt.publisher, pred.publisher)

    if field == "doi":
        return _compare_simple_string(gt.doi, pred.doi)

    if field in ("e_isbn", "p_isbn"):
        return _compare_set(getattr(gt, field), getattr(pred, field))

    if field == "e_issn":
        return _compare_e_issn(gt.e_issn, pred.e_issn, gt.p_issn)

    if field == "p_issn":
        return _compare_simple_string(gt.p_issn, pred.p_issn)

    if field == "type_coar":
        return _compare_simple_string(gt.type_coar, pred.type_coar)

    # Fallback for unknown fields.
    return _compare_simple_string(getattr(gt, field), getattr(pred, field))


# ---------------------------------------------------------------------------
# Main evaluation entry point
# ---------------------------------------------------------------------------


def run_evaluation(
    backend: BaseBackend, records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Run extraction against each record and compare with ground truth.

    For each record the PDF at ``record["url"]`` is downloaded, metadata
    is extracted using *backend*, and each field is compared against the
    ground truth parsed through :class:`PublicationMetadata`.

    Args:
        backend: Configured backend instance for extraction.
        records: Ground truth records loaded from JSONL files.

    Returns:
        List of per-field result dictionaries containing
        ``url``, ``language``, ``field``, ``predicted_val``,
        ``true_val``, ``match_type``, and ``score``.
    """
    results: list[dict[str, Any]] = []

    with Downloader() as downloader:
        for record in records:
            url = record.get("url")
            if url is None:
                continue

            filepath = downloader.download(url)
            extracted = asyncio.run(backend.extract([filepath]))

            # Parse ground truth through the same model to normalise keys.
            gt_dict = record.get("ground_truth") or {}
            gt = PublicationMetadata(**gt_dict)

            language = gt.language

            for field in PublicationMetadata.model_fields:
                match_type, score = _compare_field(field, gt, extracted)
                results.append(
                    {
                        "url": url,
                        "language": language,
                        "field": field,
                        "predicted_val": getattr(extracted, field),
                        "true_val": getattr(gt, field),
                        "match_type": match_type,
                        "score": score,
                    }
                )

    return results


def aggregate_results(
    results: list[dict[str, Any]], fields: tuple[str, ...] | None = None
) -> str:
    """Aggregate per-field results into a TSV summary table.

    Groups by (language, field) and reports mean score and count.

    Args:
        results: Per-field result list from :func:`run_evaluation`.
        fields: Optional subset of fields to include.

    Returns:
        TSV-formatted string with header row and grouped data.
    """
    if fields is not None:
        results = [r for r in results if r["field"] in fields]

    # Group by (language, field).
    groups: dict[tuple[str | None, str], list[float]] = {}
    for r in results:
        key = (r["language"], r["field"])
        groups.setdefault(key, []).append(r["score"])

    # Build sorted rows.
    rows: list[tuple[str | None, str, float, int]] = []
    for (lang, field), scores in sorted(groups.items()):
        mean_score = sum(scores) / len(scores)
        rows.append((lang, field, mean_score, len(scores)))

    # Format as TSV.
    lines = ["language\tfield\tmean_score\tcount"]
    for lang, field, mean_score, count in rows:
        lang_str = lang if lang else ""
        lines.append(f"{lang_str}\t{field}\t{mean_score:.4f}\t{count}")

    return "\n".join(lines)
