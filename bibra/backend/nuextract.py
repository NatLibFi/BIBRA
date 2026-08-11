"""Backend for metadata extraction using nuextract3 vision model."""

import json
import logging
from pathlib import Path

import pymupdf
from openai import AsyncOpenAI
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from bibra.backend.config import GlobalLLMConfig, NuExtractConfig
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


# Pages to render: first six pages + last two pages
PAGES = [0, 1, 2, 3, 4, 5, -2, -1]


def _pdf_pages_to_binary_content(pdf_path: str, dpi: int = 170) -> list[BinaryContent]:
    """Render a subset of pages from a PDF (first 6 + last 2) as BinaryContent
    for pydantic_ai.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for page rendering.

    Returns:
        List of BinaryContent objects with PNG data.
    """
    contents: list[BinaryContent] = []

    with pymupdf.open(pdf_path) as doc:
        valid_indices = sorted(
            {
                idx if idx >= 0 else len(doc) + idx
                for idx in PAGES
                if -len(doc) <= idx < len(doc)
            }
        )

        for page_idx in valid_indices:
            pix = doc[page_idx].get_pixmap(dpi=dpi, alpha=False)
            contents.append(
                BinaryContent(data=pix.tobytes("png"), media_type="image/png")
            )

    return contents


class NuExtractBackend:
    """Backend for metadata extraction using nuextract3 vision model."""

    def __init__(
        self,
        global_cfg: GlobalLLMConfig | None = None,
        nuextract_cfg: NuExtractConfig | None = None,
    ):
        """Initialize the NuExtract backend.

        Args:
            global_cfg: Global LLM configuration. If None, uses defaults.
            nuextract_cfg: NuExtract-specific configuration. If None, uses defaults.
        """
        self.global_cfg = global_cfg or GlobalLLMConfig()
        self.nuextract_cfg = nuextract_cfg or NuExtractConfig()

        api_key = self.global_cfg.api_key or "dummy-api-key"

        openai_client = AsyncOpenAI(
            base_url=self.global_cfg.endpoint_url,
            api_key=api_key,
        )

        provider = OpenAIProvider(openai_client=openai_client)

        model = OpenAIChatModel(
            model_name=self.nuextract_cfg.model,
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
            image_contents = _pdf_pages_to_binary_content(
                pdf_path, dpi=self.nuextract_cfg.dpi
            )
        except Exception:
            logger.exception("Failed to convert PDF to images: %s", pdf_path)
            return PublicationMetadata()

        if not image_contents:
            logger.warning("No pages extracted from PDF: %s", pdf_path)
            return PublicationMetadata()

        chat_template_kwargs: dict = {
            "template": json.dumps(NUEXTRACT_TEMPLATE, indent=4),
            "enable_thinking": self.nuextract_cfg.thinking,
        }
        if self.nuextract_cfg.instructions:
            chat_template_kwargs["instructions"] = self.nuextract_cfg.instructions

        user_message = [
            "Extract metadata from this document. Return as JSON.",
            *image_contents,
        ]

        result = await self.agent.run(
            user_message,
            model_settings={
                "extra_body": {
                    "chat_template_kwargs": chat_template_kwargs,
                }
            },
        )
        return result.output
