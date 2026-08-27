"""PDF content extraction using PyMuPDF and token-based chunk selection.

This module extracts metadata and selected text chunks from PDF documents,
using a scoring system to select the most informative content within a
token budget.
"""

import collections
import logging
from typing import Any

import pymupdf
import pymupdf4llm
import regex
import tiktoken

logger = logging.getLogger(__name__)

# Pages to analyze: first six pages + last two pages
PAGES: list[int] = [0, 1, 2, 3, 4, 5, -2, -1]
# Limit on how many tokens per document to include (approximately)
TOKEN_BUDGET: int = 1536
# Which OpenAI LLM tokenizer to use for counting approx tokens
TOKEN_MODEL: str = "gpt-4o-mini"
TOKEN_ENCODING = tiktoken.encoding_for_model(TOKEN_MODEL)
# PDF metadata fields not to include in extracted text
PDF_METADATA_SKIP: set[str] = {"format", "creator", "producer"}


def _comma_proportion(chunk: str) -> float:
    """Return the proportion of comma/semicolon characters in chunk."""
    if not chunk:
        return 0
    return (chunk.count(",") + chunk.count(";")) / len(chunk)


def _emph_proportion(chunk: str) -> float:
    """Return the proportion of emphasis characters in chunk."""
    if not chunk:
        return 0
    return (chunk.count("_") + chunk.count("*")) / len(chunk)


def _chunk_score(
    chunk: str, page_num: int
) -> tuple[float, set[str]] | tuple[None, None]:
    """Score a text chunk to determine its informativeness.

    Returns a tuple of (score, feats) or (None, None) for low-quality chunks.
    """
    if not chunk.strip() or chunk == "-----":
        return None, None
    if "....." in chunk or ". . . . ." in chunk or "_ _ _ _ _" in chunk:
        return None, None
    if regex.match(r"^\W+$", chunk):
        return None, None

    score = -len(chunk) - 1000 * int(page_num / 2)
    feats: set[str] = set()

    if regex.search(r"(?<!\d)20\d\d(?!\d)", chunk):
        score += 500
        feats.add("year")
    if regex.search(r"\bdoi\b", chunk, regex.IGNORECASE):
        score += 1000
        feats.add("doi")
    if regex.search(r"\bisbn\b", chunk, regex.IGNORECASE):
        score += 1000
        feats.add("isbn")
    if regex.search(r"\bissn\b", chunk, regex.IGNORECASE):
        score += 1000
        feats.add("issn")
    if regex.search(r"\bhttps?\b", chunk, regex.IGNORECASE):
        score += 1000
        feats.add("http")
    if chunk.startswith("#"):
        score += 1000
        feats.add("headline")
    if _comma_proportion(chunk) > 0.01:
        score += 10000 * _comma_proportion(chunk)
        feats.add("commas")
    if _emph_proportion(chunk) > 0.01:
        score += 10000 * _emph_proportion(chunk)
        feats.add("emph")

    return score, feats


def _split_text(text: str) -> list[str]:
    """Split text into paragraphs using Markdown-style heading detection."""
    return regex.split(r"\n+(?=[#_*]*\p{Lu})", text, flags=regex.UNICODE)


def _count_tokens(text: str) -> int:
    """Approximate token count using the specified model's tokenizer."""
    return len(TOKEN_ENCODING.encode(text))


def extract_content(file_path: str) -> dict[str, Any]:
    """Extract and return PDF metadata and selected text chunks from a PDF file.

    Args:
        file_path: Path to the PDF file.

    Returns:
        A dict with keys:
            - "pdfinfo": dict of extracted metadata fields
            - "pages": list of dicts with "page" (int) and "text" (str) keys
    """
    pdfinfo: dict[str, Any] = {}
    page_content: dict[int, list[str]] = collections.defaultdict(list)

    with pymupdf.open(file_path) as doc:
        # Extract metadata (skipping unwanted fields)
        for key in doc.metadata:
            if key not in PDF_METADATA_SKIP and doc.metadata.get(key):
                pdfinfo[key] = doc.metadata.get(key)

        # Extract valid pages, remove duplicates, and sort numerically
        all_pages = list(range(len(doc)))
        valid_indices = [idx for idx in PAGES if -len(doc) <= idx < len(doc)]
        pages_to_extract = sorted({all_pages[idx] for idx in valid_indices})

        # Extract text from selected pages
        page_texts = pymupdf4llm.to_markdown(
            doc,
            pages=pages_to_extract,
            page_chunks=True,
            show_progress=False,
            ignore_images=True,
            ignore_graphics=True,
            use_ocr=False,
        )

    # Score all chunks
    all_chunks: list[dict[str, Any]] = []
    for page in page_texts:
        page_num = page.get("metadata", {}).get("page_number", 0)

        for chunk in _split_text(page["text"]):
            score, feats = _chunk_score(chunk, page_num)
            if score is not None:
                all_chunks.append(
                    {
                        "text": chunk,
                        "page": page_num,
                        "score": score,
                        "feats": feats,
                        "index": len(all_chunks),
                        "length": _count_tokens(chunk),
                    }
                )

    # Select chunks within token budget
    selected_indices: set[int] = set()
    total_length = 0
    for chunk in sorted(all_chunks, key=lambda x: x["score"], reverse=True):
        if total_length + 1 + chunk["length"] <= TOKEN_BUDGET:
            selected_indices.add(chunk["index"])
            total_length += chunk["length"]

    # Group selected chunks by page
    for chunk in all_chunks:
        if chunk["index"] in selected_indices:
            page_content[chunk["page"]].append(chunk["text"])

    pages: list[dict[str, Any]] = []
    for pageno in sorted(page_content.keys()):
        text = "\n".join(page_content[pageno])
        pages.append({"page": pageno, "text": text})

    return {"pdfinfo": pdfinfo, "pages": pages}
