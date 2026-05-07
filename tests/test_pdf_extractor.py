"""Tests for the PDF extractor module."""

import pytest

import os

from bibra.backend.pdf_extractor import (
    TOKEN_BUDGET,
    TOKEN_MODEL,
    PDF_METADATA_SKIP,
    PAGES,
    _chunk_score,
    _comma_proportion,
    _count_tokens,
    _emph_proportion,
    _split_text,
    extract_content,
)


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "cypress", "fixtures")
SAMPLE_PDF = os.path.join(FIXTURE_DIR, "test-document.pdf")


class TestCommaProportion:
    """Tests for _comma_proportion function."""

    def test_empty_string(self):
        """Empty string should return 0."""
        assert _comma_proportion("") == 0

    def test_no_commas(self):
        """String without commas should return 0."""
        assert _comma_proportion("hello world") == 0

    def test_only_commas(self):
        """String of only commas should return 1."""
        assert _comma_proportion(",,,") == 1.0

    def test_mixed_semicolons(self):
        """String with commas and semicolons should count both."""
        result = _comma_proportion("a,b;c")
        assert result == 0.4  # 2 separators in 5 chars


class TestEmphProportion:
    """Tests for _emph_proportion function."""

    def test_empty_string(self):
        """Empty string should return 0."""
        assert _emph_proportion("") == 0

    def test_no_emphasis(self):
        """String without emphasis chars should return 0."""
        assert _emph_proportion("hello world") == 0

    def test_only_asterisks(self):
        """String of only asterisks should return 1."""
        assert _emph_proportion("***") == 1.0

    def test_mixed_emphasis(self):
        """String with both _ and * should count both."""
        result = _emph_proportion("a*b_c")
        assert result == 0.4  # 2 emph chars in 5 chars


class TestChunkScore:
    """Tests for _chunk_score function."""

    def test_empty_chunk(self):
        """Empty chunk should return (None, None)."""
        score, feats = _chunk_score("", 0)
        assert score is None
        assert feats is None

    def test_whitespace_only_chunk(self):
        """Whitespace-only chunk should return (None, None)."""
        score, feats = _chunk_score("   ", 0)
        assert score is None
        assert feats is None

    def test_dots_only_chunk(self):
        """Chunk with only dots should return (None, None)."""
        score, feats = _chunk_score(".....", 0)
        assert score is None
        assert feats is None

    def test_non_word_chunk(self):
        """Chunk with only non-word chars should return (None, None)."""
        score, feats = _chunk_score("!!!", 0)
        assert score is None
        assert feats is None

    def test_year_detection(self):
        """Chunk with a year should get +500 score and 'year' feat."""
        score, feats = _chunk_score("Published in 2024", 0)
        assert score is not None
        assert "year" in feats

    def test_doi_detection(self):
        """Chunk with DOI should get +1000 score and 'doi' feat."""
        score, feats = _chunk_score("DOI: 10.1234/test", 0)
        assert score is not None
        assert "doi" in feats

    def test_isbn_detection(self):
        """Chunk with ISBN should get +1000 score and 'isbn' feat."""
        score, feats = _chunk_score("ISBN: 978-0-123456-78-9", 0)
        assert score is not None
        assert "isbn" in feats

    def test_issn_detection(self):
        """Chunk with ISSN should get +1000 score and 'issn' feat."""
        score, feats = _chunk_score("ISSN: 1234-5678", 0)
        assert score is not None
        assert "issn" in feats

    def test_http_detection(self):
        """Chunk with URL should get +1000 score and 'http' feat."""
        score, feats = _chunk_score("https://example.com", 0)
        assert score is not None
        assert "http" in feats

    def test_headline_detection(self):
        """Chunk starting with # should get +1000 score and 'headline' feat."""
        score, feats = _chunk_score("# Introduction", 0)
        assert score is not None
        assert "headline" in feats

    def test_high_comma_proportion(self):
        """Chunk with high comma proportion should get bonus score."""
        score, feats = _chunk_score("a,b,c,d,e,f,g", 0)
        assert score is not None
        assert "commas" in feats

    def test_high_emph_proportion(self):
        """Chunk with high emphasis proportion should get bonus score."""
        score, feats = _chunk_score("*a*b*c*d*", 0)
        assert score is not None
        assert "emph" in feats

    def test_page_penalty(self):
        """Later pages should get a score penalty."""
        score0, _ = _chunk_score("Test content here", 0)
        score5, _ = _chunk_score("Test content here", 5)
        assert score5 < score0  # later page has lower score


class TestSplitText:
    """Tests for _split_text function."""

    def test_single_paragraph(self):
        """Single paragraph should return as single element."""
        result = _split_text("Single paragraph")
        assert len(result) == 1
        assert result[0] == "Single paragraph"

    def test_split_on_heading(self):
        """Text with Markdown headings should split correctly."""
        text = "Intro\n# Heading\nContent after heading"
        result = _split_text(text)
        assert len(result) >= 2

    def test_split_on_uppercase(self):
        """Text with newline before uppercase should split."""
        text = "intro\nIntroduction follows"
        result = _split_text(text)
        assert len(result) >= 2


class TestCountTokens:
    """Tests for _count_tokens function."""

    def test_empty_string(self):
        """Empty string should return 0 tokens."""
        assert _count_tokens("") == 0

    def test_simple_text(self):
        """Simple text should return positive token count."""
        count = _count_tokens("hello world")
        assert count > 0

    def test_token_model(self):
        """Should use the configured token model."""
        assert TOKEN_MODEL == "gpt-4o-mini"


class TestExtractContent:
    """Tests for extract_content function."""

    def test_extract_content_returns_dict(self):
        """extract_content should return a dict."""
        if not os.path.exists(SAMPLE_PDF):
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        result = extract_content(SAMPLE_PDF)
        assert isinstance(result, dict)

    def test_extract_content_has_pdfinfo(self):
        """Result should contain pdfinfo key."""
        if not os.path.exists(SAMPLE_PDF):
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        result = extract_content(SAMPLE_PDF)
        assert "pdfinfo" in result
        assert isinstance(result["pdfinfo"], dict)

    def test_extract_content_has_pages(self):
        """Result should contain pages key."""
        if not os.path.exists(SAMPLE_PDF):
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        result = extract_content(SAMPLE_PDF)
        assert "pages" in result
        assert isinstance(result["pages"], list)

    def test_extract_content_pages_have_required_keys(self):
        """Each page entry should have page and text keys."""
        if not os.path.exists(SAMPLE_PDF):
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        result = extract_content(SAMPLE_PDF)
        for page_entry in result["pages"]:
            assert "page" in page_entry
            assert "text" in page_entry
            assert isinstance(page_entry["page"], int)
            assert isinstance(page_entry["text"], str)

    def test_extract_content_pages_sorted(self):
        """Pages should be sorted by page number."""
        if not os.path.exists(SAMPLE_PDF):
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        result = extract_content(SAMPLE_PDF)
        page_numbers = [p["page"] for p in result["pages"]]
        assert page_numbers == sorted(page_numbers)

    def test_extract_content_within_token_budget(self):
        """Total tokens should not exceed TOKEN_BUDGET."""
        if not os.path.exists(SAMPLE_PDF):
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        result = extract_content(SAMPLE_PDF)
        total_tokens = sum(_count_tokens(p["text"]) for p in result["pages"])
        assert total_tokens <= TOKEN_BUDGET

    def test_extract_content_skips_unwanted_metadata(self):
        """pdfinfo should not contain skipped metadata fields."""
        if not os.path.exists(SAMPLE_PDF):
            pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")
        result = extract_content(SAMPLE_PDF)
        for key in PDF_METADATA_SKIP:
            assert key not in result["pdfinfo"]

    def test_extract_content_nonexistent_file(self):
        """extract_content should raise exception for non-existent file."""
        with pytest.raises(Exception):  # pymupdf raises its own FileNotFoundError
            extract_content("/nonexistent/file.pdf")


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_pages_contains_expected_values(self):
        """PAGES should contain first 6 and last 2 page indices."""
        assert 0 in PAGES
        assert 1 in PAGES
        assert 5 in PAGES
        assert -2 in PAGES
        assert -1 in PAGES

    def test_token_budget_positive(self):
        """TOKEN_BUDGET should be positive."""
        assert TOKEN_BUDGET > 0

    def test_pdf_metadata_skip_contains_expected_keys(self):
        """PDF_METADATA_SKIP should contain expected keys."""
        assert "format" in PDF_METADATA_SKIP
        assert "creator" in PDF_METADATA_SKIP
        assert "producer" in PDF_METADATA_SKIP
