"""Page selection helpers for PDF extraction.

User-facing page numbers are 1-based (as in print dialogs): positive
values count from the first page, negative values count from the last
page. Page specifications may be written as a comma-separated list
(e.g. ``1,2,3,-1``) or with ``-`` ranges (e.g. ``1-4,-2--1``).
"""

import re
from typing import Annotated, Any

from pydantic import Field
from pydantic.functional_validators import BeforeValidator

# Default pages: first six + last two, matching the previous hardcoded
# backend behavior.
DEFAULT_PAGES: list[int] = [1, 2, 3, 4, 5, 6, -2, -1]

# Maximum number of pages accepted in a single specification.
MAX_PAGES: int = 8

# A number with an optional range. The range group is anchored on the
# literal dash, so the digit runs can never be split in more than one
# way; this keeps matching linear even on inputs of many digits, e.g.
# -2--1 or a bare 1000000000.
_ITEM_RE = re.compile(r"(-?\d+)(?:\s*-\s*(-?\d+))?")
# One comma-separated item: a number or a range of numbers.
_ITEM_PATTERN = r"-?\d+(?:\s*-\s*-?\d+)?"
# Full page specification: comma-separated items, optional whitespace.
PAGES_PATTERN = rf"^\s*(?:{_ITEM_PATTERN}\s*(?:,\s*{_ITEM_PATTERN}\s*)*)?$"
# Variant for API form fields: multipart/form-data serializes an absent
# (null) value as the literal string "None", which must also be accepted.
PAGES_OR_NONE_PATTERN = rf"^(?:{PAGES_PATTERN[1:-1]}|None)$"


def _parse_item(item: str) -> list[int]:
    """Expand one comma-separated item into 1-based page numbers."""
    m = _ITEM_RE.fullmatch(item)
    if not m:
        raise ValueError(f"Invalid page specification item: {item!r}")
    start = int(m.group(1))
    if m.group(2) is None:
        return [start]
    end = int(m.group(2))
    if abs(start - end) + 1 > MAX_PAGES:
        raise ValueError(
            f"Page range {item.strip()!r} spans "
            f"{abs(start - end) + 1} pages; at most {MAX_PAGES} allowed"
        )
    if start == end:
        return [start]
    if start < end:
        return list(range(start, end + 1))
    return list(range(start, end - 1, -1))


def parse_page_spec(spec: str) -> list[int]:
    """Parse a page specification string into a list of 1-based page numbers.

    Accepts comma-separated items (``1,2,3,-1``) and ranges (``1-4``,
    ``-2--1``). Whitespace around items is ignored.

    Args:
        spec: Page specification string.

    Returns:
        List of 1-based page numbers in the order given.

    Raises:
        ValueError: If the specification is empty, contains invalid
            items, or expands to more than MAX_PAGES pages.
    """
    text = spec.strip()
    if not text:
        raise ValueError("Empty page specification")
    pages: list[int] = []
    for raw in text.split(","):
        item = raw.strip()
        pages.extend(_parse_item(item))
        if len(pages) > MAX_PAGES:
            raise ValueError(
                f"Page specification lists {len(pages)} pages; "
                f"at most {MAX_PAGES} allowed"
            )
    return pages


def parse_pages(v: Any) -> Any:
    """Coerce a pages setting (list or spec string) to 1-based page numbers.

    Use as a ``BeforeValidator`` for a ``list[int]`` field. Specification
    strings are parsed here; all other values are passed through unchanged
    so that Pydantic's ``list[int]`` validation reports proper
    ``ValidationError`` for invalid types or non-integer items.

    Args:
        v: Raw pages value from configuration.

    Returns:
        Parsed page list for string input, or the original value otherwise.

    Raises:
        ValueError: If the string specification is invalid.
    """
    if isinstance(v, str):
        return parse_page_spec(v)
    return v


PagesList = Annotated[list[int], BeforeValidator(parse_pages), Field(min_length=1)]


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
