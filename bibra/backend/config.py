"""Configuration management for BIBRA application.

This module provides configuration handling using environment variables
with support for .env files via python-dotenv.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _parse_bool(value: str | None, default: bool) -> bool:
    """Parse a boolean from an env var string (1/0/true/false, case insensitive)."""
    if value is None:
        return default
    return value.strip().lower() in ("1", "true")


def _parse_int(value: str | None, default: int) -> int:
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
            return default
        return result
    except (ValueError, TypeError):
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
        GREYLITLM_INSTRUCTIONS: Instruction template for GreyLitLM
    """

    def __init__(
        self,
        model: str | None = None,
        system_prompt: str | None = None,
        instructions: str | None = None,
    ):
        """Initialize GreyLitLM configuration.

        Args:
            model: Model name. Defaults to env var or "greylitlm".
            system_prompt: System prompt. Defaults to env var or built-in default.
            instructions: Instruction template. Defaults to env var or built-in default.
        """
        self.model = (
            model if model is not None else os.getenv("GREYLITLM_MODEL", "greylitlm")
        )
        self.system_prompt = (
            system_prompt
            if system_prompt is not None
            else os.getenv(
                "GREYLITLM_SYSTEM_PROMPT",
                "You are a skilled librarian specialized in meticulous cataloguing of"
                " digital documents.",
            )
        )
        self.instructions = (
            instructions
            if instructions is not None
            else os.getenv(
                "GREYLITLM_INSTRUCTIONS",
                "Extract metadata from this document. Return as JSON.",
            )
        )


class NuExtractConfig:
    """NuExtract-specific settings.

    Environment Variables:
        NUEXTRACT_MODEL: Model name for NuExtract (default: nuextract3)
        NUEXTRACT_THINKING: Enable thinking mode (default: False)
        NUEXTRACT_INSTRUCTIONS: Custom instructions for NuExtract (optional)
        NUEXTRACT_DPI: DPI for PDF-to-image conversion (default: 170)
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
            model: Model name. Defaults to env var or "nuextract3".
            thinking: Enable thinking mode. Defaults to env var or False.
            instructions: Custom instructions. Defaults to env var value.
            dpi: DPI for PDF-to-image conversion. Defaults to env var or 170.
        """
        self.model = (
            model if model is not None else os.getenv("NUEXTRACT_MODEL", "nuextract3")
        )
        self.thinking = _parse_bool(
            os.getenv("NUEXTRACT_THINKING") if thinking is None else str(thinking),
            default=False,
        )
        self.instructions = (
            instructions
            if instructions is not None
            else os.getenv("NUEXTRACT_INSTRUCTIONS", "")
        )
        self.dpi = _parse_int(
            os.getenv("NUEXTRACT_DPI") if dpi is None else str(dpi),
            default=170,
        )


def get_global_llm_config() -> GlobalLLMConfig:
    """Get the global LLM configuration.

    Returns:
        GlobalLLMConfig: The current global LLM configuration.
    """
    return GlobalLLMConfig()


def get_greylitlm_config() -> GreyLitLMConfig:
    """Get the GreyLitLM configuration.

    Returns:
        GreyLitLMConfig: The current GreyLitLM configuration.
    """
    return GreyLitLMConfig()


def get_nuextract_config() -> NuExtractConfig:
    """Get the NuExtract configuration.

    Returns:
        NuExtractConfig: The current NuExtract configuration.
    """
    return NuExtractConfig()
