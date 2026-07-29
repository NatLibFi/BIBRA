"""Backend for metadata extraction using nuextract3 vision model."""

import json
import logging
from pathlib import Path

import pymupdf
from openai import AsyncOpenAI
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from bibra.backend.config import LLMConfig
from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)

COAR_TYPES = [
    "master thesis",
    "bachelor thesis",
    "thesis",
    "doctoral thesis",
    "research report",
    "report",
    "book",
    "book part",
    "journal article",
    "research article",
    "newspaper article",
    "conference paper",
    "blog post",
    "book review",
    "editorial",
    "review article",
    "policy report",
    "learning object",
    "other",
    "artistic work",
    "technical documentation",
    "conference paper not in proceedings",
    "conference output",
    "text",
    "memorandum",
    "collection",
    "working paper",
    "project deliverable",
]

# Default extraction template matching nuextract3 expectations
NUEXTRACT_TEMPLATE = {
    "language": "language-tag",
    "title": "string",
    "alt_title": "string",
    "creator": ["string"],
    "year": "date",
    "publisher": ["string"],
    "doi": "string",
    "e-isbn": ["string"],
    "p-isbn": ["string"],
    "e-issn": "string",
    "p-issn": "string",
    "type_coar": COAR_TYPES,
}


def _pdf_pages_to_binary_content(pdf_path: str, dpi: int = 170) -> list[BinaryContent]:
    """Render each page of a PDF as a BinaryContent for pydantic_ai.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for page rendering.

    Returns:
        List of BinaryContent objects with PNG data.
    """
    contents: list[BinaryContent] = []

    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            png_bytes = pix.tobytes("png")
            contents.append(BinaryContent(data=png_bytes, media_type="image/png"))

    return contents


class NuExtractBackend:
    """Backend for metadata extraction using nuextract3 vision model."""

    def __init__(self, config: LLMConfig | None = None):
        """Initialize the NuExtract backend.

        Args:
            config: LLM configuration. If None, uses default LLMConfig.
        """
        self.config = config or LLMConfig()

        api_key = self.config.LLM_API_KEY or "dummy-api-key"

        openai_client = AsyncOpenAI(
            base_url=self.config.LLM_ENDPOINT_URL,
            api_key=api_key,
        )

        provider = OpenAIProvider(openai_client=openai_client)

        model = OpenAIChatModel(
            model_name=self.config.NUEXTRACT_MODEL,
            provider=provider,
        )

        self.agent = Agent(
            model,
            output_type=PublicationMetadata,
        )

    async def extract(self, file_paths: list[str]) -> PublicationMetadata:
        """Extract publication metadata from a PDF file using vision.

        Args:
            file_paths: List of file paths. Only the first PDF is used.

        Returns:
            PublicationMetadata: Extracted metadata.
        """
        # Find first PDF file
        pdf_path = None
        for path in file_paths:
            if Path(path).suffix.lower() == ".pdf":
                pdf_path = path
                break

        if pdf_path is None:
            logger.warning("No PDF file found in uploaded files")
            return PublicationMetadata()

        try:
            image_contents = _pdf_pages_to_binary_content(pdf_path)
        except Exception:
            logger.exception("Failed to convert PDF to images: %s", pdf_path)
            return PublicationMetadata()

        if not image_contents:
            logger.warning("No pages extracted from PDF: %s", pdf_path)
            return PublicationMetadata()

        # Build user message with text + images
        user_message = [
            "Extract metadata from this document. Return as JSON.",
            *image_contents,
        ]

        try:
            result = await self.agent.run(
                user_message,
                model_settings={
                    "extra_body": {
                        "chat_template_kwargs": {
                            "template": json.dumps(NUEXTRACT_TEMPLATE, indent=4),
                            "enable_thinking": False,
                        }
                    }
                },
            )
            return result.output
        except Exception:
            logger.exception("Failed to extract metadata from PDF: %s", pdf_path)
            return PublicationMetadata()
