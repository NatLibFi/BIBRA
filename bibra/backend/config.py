"""Configuration management for BIBRA application.

This module provides configuration handling using environment variables
with support for .env files via python-dotenv.
"""

from dotenv import load_dotenv

import os

from typing import Optional

load_dotenv()


class LLMConfig:
    """Configuration for LLM endpoint.

    Environment Variables:
        LLM_ENDPOINT_URL: The URL of the LLM endpoint (default: http://localhost:8080/v1/)
        LLM_API_KEY: API key for authentication (optional, can be None)
    """

    LLM_ENDPOINT_URL: str = os.getenv("LLM_ENDPOINT_URL", "http://localhost:8080/v1/")
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "greylitlm")

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
