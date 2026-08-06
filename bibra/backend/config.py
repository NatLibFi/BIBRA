"""Configuration management for BIBRA application.

This module provides configuration handling using environment variables
with support for .env files via python-dotenv.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()


logger = logging.getLogger(__name__)


def _parse_bool(value: str | None, default: bool, key: str | None = None) -> bool:
    """Parse a boolean from an env var string (1/0/true/false, case insensitive).

    Falls back to `default` for unrecognized or empty values.

    Args:
        value: The string value to parse.
        default: The default value to return on failure or unrecognized input.

    Returns:
        The parsed boolean, or the default if parsing fails or the value is
        unrecognized.
    """
    if value is None:
        logger.warning("Config %s is not set, using default %r", key, default)
        return default
    stripped = value.strip().lower()
    if stripped in ("1", "true"):
        return True
    if stripped in ("0", "false"):
        return False
    logger.warning(
        "Invalid config value %r for %s, using default %r",
        value,
        key,
        default,
    )
    return default


def _parse_int(value: str | None, default: int, key: str | None = None) -> int:
    """Parse an integer from an env var string, falling back to default on failure.

    Non-positive values are also treated as invalid and fall back to the default.

    Args:
        value: The string value to parse.
        default: The default value to return on failure.

    Returns:
        The parsed integer, or the default if parsing fails or the value is
        non-positive.
    """
    if value is None:
        return default
    try:
        result = int(value.strip())
        if result <= 0:
            logger.warning(
                "Invalid config value %r for %s (non-positive), using default %r",
                value,
                key,
                default,
            )
            return default
        return result
    except (ValueError, TypeError):
        logger.warning(
            "Invalid config value %r for %s, using default %r",
            value,
            key,
            default,
        )
    return default


class GlobalLLMConfig:
    """Shared LLM infrastructure settings.

    Environment Variables:
        LLM_ENDPOINT_URL: The URL of the LLM endpoint (default: http://localhost:8080/v1/)
        LLM_API_KEY: API key for authentication (optional, can be None)
    """

    def __init__(
        self,
        endpoint_url: str | None = None,
        api_key: str | None = None,
    ):
        """Initialize global LLM configuration.

        Args:
            endpoint_url: The URL of the LLM endpoint. Defaults to env var or
                http://localhost:8080/v1/.
            api_key: API key for authentication. Defaults to env var value.
        """
        self.endpoint_url = (
            endpoint_url
            if endpoint_url is not None
            else os.getenv("LLM_ENDPOINT_URL", "http://localhost:8080/v1/")
        )
        self.api_key = api_key if api_key is not None else os.getenv("LLM_API_KEY")


class GreyLitLMConfig:
    """GreyLitLM-specific settings.

    Environment Variables:
        GREYLITLM_MODEL: Model name for GreyLitLM (default: greylitlm)
        GREYLITLM_SYSTEM_PROMPT: System prompt for GreyLitLM
        GREYLITLM_INSTRUCTIONS: Instructions for GreyLitLM
    """

    def __init__(
        self,
        model: str | None = None,
        system_prompt: str | None = None,
        instructions: str | None = None,
    ):
        """Initialize GreyLitLM configuration.

        Args:
            model: Model name. Defaults to "greylitlm".
            system_prompt: System prompt. Defaults to built-in default.
            instructions: Instructions. Defaults to built-in default.
        """
        self.model = model if model is not None else "greylitlm"
        self.system_prompt = (
            system_prompt
            if system_prompt is not None
            else (
                "You are a skilled librarian specialized in meticulous cataloguing of"
                " digital documents."
            )
        )
        self.instructions = (
            instructions
            if instructions is not None
            else "Extract metadata from this document. Return as JSON."
        )


class NuExtractConfig:
    """NuExtract-specific settings.

    All configuration comes from constructor arguments (typically from
    ``projects.toml`` with ``${VAR}`` interpolation for secrets/URLs).
    """

    def __init__(
        self,
        model: str | None = None,
        thinking: bool | None = None,
        instructions: str | None = None,
        dpi: int | None = None,
    ):
        """Initialize NuExtract configuration.

        Args:
            model: Model name. Defaults to "nuextract3".
            thinking: Enable thinking mode. Defaults to ``False``.
            instructions: Custom instructions. Defaults to empty string.
            dpi: DPI for PDF-to-image conversion. Defaults to 170.
        """
        self.model = model if model is not None else "nuextract3"
        self.thinking = _parse_bool(
            str(thinking) if thinking is not None else "False",
            default=False,
            key="NUEXTRACT_THINKING",
        )
        self.instructions = instructions if instructions is not None else ""
        self.dpi = _parse_int(str(dpi) if dpi is not None else None, default=170)
