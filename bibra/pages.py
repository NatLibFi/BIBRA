"""Page selection helpers for PDF extraction.

User-facing page numbers are 1-based (as in print dialogs): positive
values count from the first page, negative values count from the last
page. Page specifications may be written as a comma-separated list
(e.g. ``1,2,3,-1``) or with ``-`` ranges (e.g. ``1-4,-2--1``).
"""

import re

# Default pages: first six + last two, matching the previous hardcoded
# backend behavior.
DEFAULT_PAGES: list[int] = [1, 2, 3, 4, 5, 6, -2, -1]

# A number followed by an optional range whose separator and negative
# endpoints make the pattern ambiguous to simple splits, e.g. -2--1.
_RANGE_RE = re.compile(r"(-?\d+)(\s*-\s*(-?\d+))")
_NUMBER_RE = re.compile(r"-?\d+")
# One comma-separated item: a number or a range of numbers.
_ITEM_PATTERN = r"-?\d+(?:\s*-\s*-?\d+)?"
# Full page specification: comma-separated items, optional whitespace.
PAGES_PATTERN = rf"^\s*(?:{_ITEM_PATTERN}\s*(?:,\s*{_ITEM_PATTERN}\s*)*)?$"
# Variant for API form fields: multipart/form-data serializes an absent
# (null) value as the literal string "None", which must also be accepted.
PAGES_OR_NONE_PATTERN = rf"^(?:{PAGES_PATTERN[1:-1]}|None)$"


def _parse_item(item: str) -> list[int]:
    """Expand one comma-separated item into 1-based page numbers."""
    m = _RANGE_RE.fullmatch(item)
    if m:
        start, end = int(m.group(1)), int(m.group(3))
        if start == end:
            return [start]
        if start < end:
            return list(range(start, end + 1))
        return list(range(start, end - 1, -1))
    if _NUMBER_RE.fullmatch(item):
        return [int(item)]
    raise ValueError(f"Invalid page specification item: {item!r}")


def parse_page_spec(spec: str) -> list[int]:
    """Parse a page specification string into a list of 1-based page numbers.

    Accepts comma-separated items (``1,2,3,-1``) and ranges (``1-4``,
    ``-2--1``). Whitespace around items is ignored.

    Args:
        spec: Page specification string.

    Returns:
        List of 1-based page numbers in the order given.

    Raises:
        ValueError: If the specification is empty or contains invalid
            items.
    """
    text = spec.strip()
    if not text:
        raise ValueError("Empty page specification")
    pages: list[int] = []
    for raw in text.split(","):
        item = raw.strip()
        pages.extend(_parse_item(item))
    return pages


def resolve_page_indices(pages: list[int], n_pages: int) -> list[int]:
    """Convert 1-based page numbers to 0-based indices of a document.

    Out-of-range pages (positive or negative) are skipped, and the result
    is deduplicated so no page is processed twice.

    Args:
        pages: 1-based page numbers (negative = counting from the end).
        n_pages: Total number of pages in the document.

    Returns:
        Sorted, unique 0-based page indices within the document.
    """
    indices: set[int] = set()
    for p in pages:
        idx = p - 1 if p > 0 else n_pages + p
        if 0 <= idx < n_pages:
            indices.add(idx)
    return sorted(indices)
