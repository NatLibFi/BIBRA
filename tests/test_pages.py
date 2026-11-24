"""Tests for the page selection helpers."""

import pytest

from bibra.pages import (
    DEFAULT_PAGES,
    parse_page_spec,
    resolve_page_indices,
)


class TestParsePageSpec:
    """Tests for parse_page_spec."""

    def test_single_page(self):
        assert parse_page_spec("1") == [1]

    def test_comma_separated(self):
        assert parse_page_spec("1,2,3,4,-2,-1") == [1, 2, 3, 4, -2, -1]

    def test_whitespace_allowed(self):
        assert parse_page_spec(" 1 , 2 , -1 ") == [1, 2, -1]

    def test_positive_range(self):
        assert parse_page_spec("1-4") == [1, 2, 3, 4]

    def test_single_item_range(self):
        assert parse_page_spec("3-3") == [3]

    def test_reverse_positive_range(self):
        assert parse_page_spec("4-1") == [4, 3, 2, 1]

    def test_negative_range(self):
        assert parse_page_spec("-2--1") == [-2, -1]

    def test_mixed_spec(self):
        assert parse_page_spec("1-4,-2--1") == [1, 2, 3, 4, -2, -1]

    def test_empty_spec_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            parse_page_spec("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            parse_page_spec("   ")

    def test_trailing_comma_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            parse_page_spec("1,2,")

    def test_invalid_item_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            parse_page_spec("1,a")

    def test_zero_page_allowed(self):
        """Zero is syntactically valid; resolution treats it as out of range."""
        assert parse_page_spec("0") == [0]

    def test_range_with_spaces(self):
        assert parse_page_spec("1 - 3") == [1, 2, 3]

    def test_empty_range_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            parse_page_spec("1-")


class TestResolvePageIndices:
    """Tests for resolve_page_indices."""

    def test_positive_pages(self):
        assert resolve_page_indices([1, 2], 10) == [0, 1]

    def test_negative_pages(self):
        assert resolve_page_indices([-1, -2], 10) == [8, 9]

    def test_mixed_pages(self):
        assert resolve_page_indices([1, -1], 10) == [0, 9]

    def test_skips_out_of_range_positive(self):
        assert resolve_page_indices([1, 50], 10) == [0]

    def test_skips_out_of_range_negative(self):
        assert resolve_page_indices([-1, -50], 10) == [9]

    def test_skips_zero(self):
        assert resolve_page_indices([0], 10) == []

    def test_deduplicates(self):
        # Page 1 and -10 both refer to the first page of a 10-page document.
        assert resolve_page_indices([1, -10], 10) == [0]
        # Repeats are dropped.
        assert resolve_page_indices([2, 2], 10) == [1]

    def test_result_sorted(self):
        assert resolve_page_indices([-1, 1, -2], 10) == [0, 8, 9]

    def test_empty_input(self):
        assert resolve_page_indices([], 10) == []

    def test_empty_document(self):
        assert resolve_page_indices([1, -1], 0) == []

    def test_small_document(self):
        # Both pages of a 2-page document.
        assert resolve_page_indices([1, -1], 2) == [0, 1]

    def test_default_pages(self):
        assert DEFAULT_PAGES == [1, 2, 3, 4, 5, 6, -2, -1]
