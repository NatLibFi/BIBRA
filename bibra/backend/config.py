"""Configuration management for BIBRA application.

This module provides configuration handling using environment variables.
Environment variables are typically loaded from .env files via python-dotenv
at application startup (see bibra.main and bibra.cli entry points).
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def parse_bool_or_str(v: Any) -> bool:
    """Coerce bool or string representation to bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    stripped = str(v).strip().lower()
    if stripped in ("1", "true"):
        return True
    if stripped in ("0", "false"):
        return False
    logger.warning("Unrecognized bool value %r, defaulting to False", v)
    return False


def parse_int_or_str(v: Any) -> int:
    """Coerce int or string representation to int."""
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except ValueError:
        logger.warning("Unrecognized int value %r, defaulting to 0", v)
        return 0


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
