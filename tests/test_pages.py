"""Tests for the page selection helpers."""

import re
from typing import ClassVar

import pytest
from pydantic import BaseModel, ValidationError

from bibra.pages import (
    DEFAULT_PAGES,
    MAX_PAGES,
    PAGES_FORM_PATTERN,
    PAGES_SPEC_PATTERN,
    PagesList,
    parse_page_spec,
    resolve_page_indices,
)


class _PagesModel(BaseModel):
    """Probe model for PagesList validation."""

    pages: PagesList


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

    def test_zero_page_raises(self):
        """Page 0 is never a valid page and is rejected at parse time."""
        with pytest.raises(ValueError, match="Page 0"):
            parse_page_spec("0")

    def test_zero_in_forward_range_raises(self):
        with pytest.raises(ValueError, match="Page 0"):
            parse_page_spec("0-3")

    def test_zero_in_reverse_range_raises(self):
        with pytest.raises(ValueError, match="Page 0"):
            parse_page_spec("1-0")

    def test_zero_in_negative_range_raises(self):
        with pytest.raises(ValueError, match="Page 0"):
            parse_page_spec("2--2")

    def test_zero_with_other_pages_raises(self):
        with pytest.raises(ValueError, match="Page 0"):
            parse_page_spec("1,0,2")

    def test_range_with_spaces(self):
        assert parse_page_spec("1 - 3") == [1, 2, 3]

    def test_empty_range_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            parse_page_spec("1-")

    def test_range_exceeding_max_pages_raises(self):
        with pytest.raises(ValueError, match="at most"):
            parse_page_spec(f"1-{MAX_PAGES + 1}")

    def test_reverse_range_exceeding_max_pages_raises(self):
        with pytest.raises(ValueError, match="at most"):
            parse_page_spec(f"{MAX_PAGES + 1}-1")

    def test_huge_range_raises_without_materializing(self):
        with pytest.raises(ValueError, match="at most"):
            parse_page_spec("1-1000000000")

    def test_long_digit_run_is_fast(self):
        """A long run of digits must not cause quadratic regex backtracking."""
        item = "9" * 4000
        assert parse_page_spec(item) == [int(item)]

    def test_long_digit_run_range_is_fast(self):
        item = "1-" + "9" * 4000
        with pytest.raises(ValueError, match="at most"):
            parse_page_spec(item)

    def test_max_width_range_allowed(self):
        assert parse_page_spec(f"1-{MAX_PAGES}") == list(range(1, MAX_PAGES + 1))

    def test_cumulative_pages_over_max_raises(self):
        spec = ",".join(str(p) for p in range(1, MAX_PAGES + 2))
        with pytest.raises(ValueError, match="at most"):
            parse_page_spec(spec)

    def test_cumulative_mixed_over_max_raises(self):
        spec = f"1-4,5-{MAX_PAGES + 1}"
        with pytest.raises(ValueError, match="at most"):
            parse_page_spec(spec)

    def test_max_page_count_allowed(self):
        spec = ",".join(str(p) for p in range(1, MAX_PAGES + 1))
        assert parse_page_spec(spec) == list(range(1, MAX_PAGES + 1))


class TestPagesSpecPattern:
    """Tests that PAGES_SPEC_PATTERN agrees with the parse_page_spec grammar."""

    _pattern = re.compile(PAGES_SPEC_PATTERN)
    _form_pattern = re.compile(PAGES_FORM_PATTERN)

    VALID_SPECS: ClassVar[list[str]] = [
        "1",
        "-1",
        "123456789",
        "1,2,3,4,-2,-1",
        "1, 2 , -1",
        " 1-4 ",
        "1-4,-2--1",
        "1 - 3",
        "-2 --1",
        "3-3",
        "4-1",
        f"1-{MAX_PAGES}",
        "1000000000",
        f"{MAX_PAGES + 1}",
        "01",
    ]

    # Syntactically valid (pattern matches) but rejected at parse time:
    # the no-zero and page-count-cap rules are not expressible in a regex.
    DIVERGENT_SPECS: ClassVar[list[str]] = [
        "0",
        "0-3",
        "1,0,2",
        f"1-{MAX_PAGES + 1}",
        ",".join(str(p) for p in range(1, MAX_PAGES + 2)),
    ]

    INVALID_SPECS: ClassVar[list[str]] = [
        "",
        "   ",
        "None",
        "null",
        "none",
        "1,",
        ",1",
        "1,,2",
        "1,a",
        "a",
        "-",
        "--",
        "1-",
        "-1-",
        "1-2-3",
        "1..2",
        "1.5",
        "+1",
    ]

    def test_valid_specs_match_pattern(self):
        for spec in self.VALID_SPECS:
            assert self._pattern.fullmatch(spec), spec

    def test_valid_specs_parse(self):
        for spec in self.VALID_SPECS:
            parse_page_spec(spec)

    def test_invalid_specs_rejected_by_pattern(self):
        for spec in self.INVALID_SPECS:
            assert not self._pattern.fullmatch(spec), spec

    def test_invalid_specs_raise(self):
        for spec in self.INVALID_SPECS:
            with pytest.raises(ValueError):
                parse_page_spec(spec)

    def test_divergent_specs_match_pattern_but_fail_to_parse(self):
        for spec in self.DIVERGENT_SPECS:
            assert self._pattern.fullmatch(spec), spec
            with pytest.raises(ValueError):
                parse_page_spec(spec)

    def test_form_pattern_accepts_specs_and_blank(self):
        """The published form pattern is the spec grammar plus blank input."""
        for spec in self.VALID_SPECS:
            assert self._form_pattern.fullmatch(spec), spec
        for value in ("", "   "):
            assert self._form_pattern.fullmatch(value), value

    def test_form_pattern_rejects_invalid_specs(self):
        for spec in self.INVALID_SPECS:
            if not spec.strip():
                continue  # blank values are valid form input (project default)
            assert not self._form_pattern.fullmatch(spec), spec


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


class TestPagesList:
    """Tests for the PagesList annotated type."""

    def test_spec_string(self):
        assert _PagesModel(pages="1-4,-2--1").pages == [1, 2, 3, 4, -2, -1]

    def test_int_list(self):
        assert _PagesModel(pages=[1, 2, 3, -1]).pages == [1, 2, 3, -1]

    def test_empty_list_raises_validation_error(self):
        """An empty page list is rejected by the min_length constraint."""
        with pytest.raises(ValidationError, match="at least 1 item"):
            _PagesModel.model_validate({"pages": []})

    def test_scalar_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _PagesModel.model_validate({"pages": 1})

    def test_fractional_item_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _PagesModel.model_validate({"pages": [2.9]})

    def test_invalid_spec_string_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _PagesModel.model_validate({"pages": "1,a"})

    def test_none_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _PagesModel.model_validate({"pages": None})

    def test_list_at_max_length_allowed(self):
        assert _PagesModel(pages=list(range(1, MAX_PAGES + 1))).pages == list(
            range(1, MAX_PAGES + 1)
        )

    def test_list_over_max_length_raises(self):
        with pytest.raises(ValidationError, match="at most"):
            _PagesModel.model_validate({"pages": list(range(1, MAX_PAGES + 2))})

    def test_list_over_max_length_duplicates_raises(self):
        """The cap counts items, not unique pages, like the string path."""
        with pytest.raises(ValidationError, match="at most"):
            _PagesModel.model_validate({"pages": [1] * (MAX_PAGES + 1)})

    def test_spec_string_with_zero_raises_validation_error(self):
        with pytest.raises(ValidationError, match="Page 0"):
            _PagesModel.model_validate({"pages": "0"})

    def test_list_with_zero_raises_validation_error(self):
        """Explicit lists (config) are checked for 0, not just strings."""
        with pytest.raises(ValidationError, match="Page 0"):
            _PagesModel.model_validate({"pages": [1, 0, 2]})
