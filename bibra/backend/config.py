import os


class LLMConfig:
    """Configuration for LLM endpoint."""

    LLM_ENDPOINT_URL: str = os.getenv(
        "LLM_ENDPOINT_URL", "http://localhost:5000/api/extract"
    )
    LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")

    SYSTEM_PROMPT: str = "You are a skilled librarian specialized in meticulous cataloguing of digital documents."
    INSTRUCTION: str = "Extract metadata from this document. Return as JSON.\n\n{}"
