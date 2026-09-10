"""Tests for generic environment variable helpers in bibra.env."""

import pytest

from bibra.env import (
    interpolate_dict_values,
    interpolate_env_vars,
    parse_bool_env,
    parse_int_env,
    parse_list_env,
)


class TestInterpolateEnvVars:
    """Tests for interpolate_env_vars."""

    def test_none_returns_none(self):
        """Test that None input returns None."""
        assert interpolate_env_vars(None) is None

    def test_non_string_int_returns_unchanged(self):
        """Test that non-string values (int) are returned unchanged."""
        assert interpolate_env_vars(42) == 42

    def test_non_string_float_returns_unchanged(self):
        """Test that non-string values (float) are returned unchanged."""
        assert interpolate_env_vars(3.14) == 3.14

    def test_non_string_bool_returns_unchanged(self):
        """Test that non-string values (bool) are returned unchanged."""
        assert interpolate_env_vars(True) is True
        assert interpolate_env_vars(False) is False

    def test_non_string_list_returns_unchanged(self):
        """Test that non-string values (list) are returned unchanged."""
        assert interpolate_env_vars([1, 2, 3]) == [1, 2, 3]

    def test_string_with_no_placeholders_returns_unchanged(self):
        """Test that strings without placeholders are returned unchanged."""
        assert interpolate_env_vars("hello world") == "hello world"

    def test_unclosed_placeholder_returns_unchanged(self):
        """Test that strings with ${ but no closing } are returned unchanged."""
        assert interpolate_env_vars("${FOO") == "${FOO"

    def test_unclosed_placeholder_mid_string_returns_unchanged(self):
        """Test that ${ without } in the middle of a string is returned unchanged."""
        assert interpolate_env_vars("prefix ${BAR suffix") == "prefix ${BAR suffix"

    def test_unclosed_placeholder_with_trailing_text(self):
        """Test that an unclosed ${ followed by text is left as-is."""
        assert interpolate_env_vars("prefix${BAR suffix") == "prefix${BAR suffix"

    def test_set_variable_is_interpolated(self, monkeypatch):
        """Test that a set ${VAR} placeholder is replaced by its value."""
        monkeypatch.setenv("BIBRA_TEST_ENV", "value")
        assert interpolate_env_vars("pre-${BIBRA_TEST_ENV}-post") == "pre-value-post"

    def test_unset_variable_placeholder_preserved(self, monkeypatch):
        """Test that an unset ${VAR} placeholder is preserved."""
        monkeypatch.delenv("BIBRA_TEST_UNSET", raising=False)
        assert interpolate_env_vars("${BIBRA_TEST_UNSET}") == "${BIBRA_TEST_UNSET}"


class TestInterpolateDictValues:
    """Tests for interpolate_dict_values."""

    def test_interpolates_string_values_only(self, monkeypatch):
        """Only string values are interpolated; others pass through."""
        monkeypatch.setenv("BIBRA_TEST_ENV", "x")

        result = interpolate_dict_values(
            {"a": "${BIBRA_TEST_ENV}", "b": 5, "c": None, "d": "plain"}
        )
        assert result == {"a": "x", "b": 5, "c": None, "d": "plain"}

    def test_empty_dict(self):
        """An empty dict is returned unchanged."""
        assert interpolate_dict_values({}) == {}


@pytest.mark.parametrize(
    ("raw", "default", "expected"),
    [
        ("", ["fallback"], ("fallback",)),
        ("a, b", ["fallback"], ("a", "b")),
        (" ,A ,", ["fallback"], ("a",)),
    ],
)
def test_parse_list_env(monkeypatch, raw: str, default, expected):
    """parse_list_env splits, strips, lowercases; falls back on blank."""
    monkeypatch.setenv("BIBRA_TEST_LIST", raw)
    assert parse_list_env("BIBRA_TEST_LIST", list(default)) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("5", 5), ("", 7), ("-3", 7), ("abc", 7)],
)
def test_parse_int_env(monkeypatch, raw: str, expected: int):
    """parse_int_env returns positive ints, default otherwise."""
    monkeypatch.setenv("BIBRA_TEST_INT", raw)
    assert parse_int_env("BIBRA_TEST_INT", 7) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
    ],
)
def test_parse_bool_env_recognized(monkeypatch, raw: str, expected: bool):
    """parse_bool_env maps recognized true/false values exactly."""
    monkeypatch.setenv("BIBRA_TEST_BOOL", raw)
    assert parse_bool_env("BIBRA_TEST_BOOL", False) is expected
    assert parse_bool_env("BIBRA_TEST_BOOL", True) is expected


@pytest.mark.parametrize(
    ("raw", "default", "expected"),
    [
        # Unset or blank -> default
        ("", True, True),
        ("", False, False),
        ("   ", True, True),
        # Malformed values fall back to the default (not silently False)
        ("nope", True, True),
        ("TRUE2", True, True),
        ("truly", False, False),
        ("1true", True, True),
        ("onoff", False, False),
    ],
)
def test_parse_bool_env_malformed_falls_back(
    monkeypatch, raw: str, default: bool, expected: bool
):
    """Unset, blank, or malformed values fall back to the default."""
    monkeypatch.setenv("BIBRA_TEST_BOOL", raw)
    assert parse_bool_env("BIBRA_TEST_BOOL", default) is expected
