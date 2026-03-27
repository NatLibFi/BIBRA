"""Configuration management for BIBRA application.

This module provides configuration handling using environment variables
with support for .env files via python-dotenv.
"""

from typing import Optional

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import os


class LLMConfig:
    """Configuration for LLM endpoint.

    Environment Variables:
        LLM_ENDPOINT_URL: The URL of the LLM endpoint (default: http://localhost:5000/api/extract)
        LLM_API_KEY: API key for authentication (optional, can be None)
    """

    LLM_ENDPOINT_URL: str = os.getenv(
        "LLM_ENDPOINT_URL", "http://localhost:5000/api/extract"
    )
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")

    SYSTEM_PROMPT: str = (
        "You are a skilled librarian specialized in meticulous cataloguing of"
        " digital documents."
    )
    INSTRUCTION: str = "Extract metadata from this document. Return as JSON.\n\n{}"


def get_llm_config() -> LLMConfig:
    """Get the LLM configuration.

    Returns:
        LLMConfig: The current LLM configuration.
    """
    return LLMConfig()
