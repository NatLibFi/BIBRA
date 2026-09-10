"""Generic environment variable helpers.

Utilities for reading and interpreting values from ``os.environ``:
interpolating ``${VAR_NAME}`` placeholders into strings, and parsing
comma-separated lists, positive integers, and boolean flags with
sane fallbacks to defaults on unset or malformed values.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def interpolate_env_vars(value: Any) -> Any:
    """Interpolate environment variables in a string value.

    Supports ${VAR_NAME} syntax. If the environment variable is not set,
    the original placeholder is preserved.

    Args:
        value: The string value to interpolate.

    Returns:
        The interpolated string, or the input unchanged if non-string.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value

    result = value
    start = 0
    while start < len(result):
        open_pos = result.find("${", start)
        if open_pos == -1:
            break
        close_pos = result.find("}", open_pos + 2)
        if close_pos == -1:
            break

        var_name = result[open_pos + 2 : close_pos]
        env_value = os.environ.get(var_name)
        if env_value is not None:
            result = result[:open_pos] + env_value + result[close_pos + 1 :]
            start = open_pos + len(env_value)
        else:
            start = close_pos + 1

    return result


def interpolate_dict_values(d: dict[str, Any]) -> dict[str, Any]:
    """Interpolate environment variables in all string values of a dict."""
    return {
        key: interpolate_env_vars(value) if isinstance(value, str) else value
        for key, value in d.items()
    }


def parse_list_env(name: str, default: list[str]) -> tuple[str, ...]:
    """Parse a comma-separated env var into a tuple of stripped strings.

    Falls back to the default when the variable is unset or blank.
    """
    raw = os.environ.get(name, "")
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return tuple(items) if items else tuple(item.lower() for item in default)


def parse_int_env(name: str, default: int) -> int:
    """Parse a positive-integer env var, falling back to the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.debug("Invalid %s=%r; using default %d", name, raw, default)
        return default
    return value if value > 0 else default


def parse_bool_env(name: str, default: bool) -> bool:
    """Parse a boolean env var (1/true/yes/on), falling back to the default."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}
