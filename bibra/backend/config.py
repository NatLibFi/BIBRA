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


class LLMConfig:
    """Configuration for LLM endpoint.

    Environment Variables:
        LLM_ENDPOINT_URL: The URL of the LLM endpoint (default: http://localhost:8080/v1/)
        LLM_API_KEY: API key for authentication (optional, can be None)
    """

    LLM_ENDPOINT_URL: str = os.getenv("LLM_ENDPOINT_URL", "http://localhost:8080/v1/")
    LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")
    NUEXTRACT_MODEL: str = os.getenv("NUEXTRACT_MODEL", "nuextract3")
    GREYLITLM_MODEL: str = os.getenv("GREYLITLM_MODEL", "greylitlm")

    NUEXTRACT_THINKING: bool = _parse_bool(
        os.getenv("NUEXTRACT_THINKING"), default=False
    )

    SYSTEM_PROMPT: str = (
        "You are a skilled librarian specialized in meticulous cataloguing of"
        " digital documents."
    )
    INSTRUCTION: str = "Extract metadata from this document. Return as JSON.\n\n{}"

    NUEXTRACT_INSTRUCTIONS: str = os.getenv("NUEXTRACT_INSTRUCTIONS", "")


def get_llm_config() -> LLMConfig:
    """Get the LLM configuration.

    Returns:
        LLMConfig: The current LLM configuration.
    """
    return LLMConfig()
