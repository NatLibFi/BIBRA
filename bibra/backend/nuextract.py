"""Backend for metadata extraction using nuextract3 vision model."""

import json
import logging
from pathlib import Path
from typing import Annotated, Any

import pymupdf
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_validators import BeforeValidator
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from bibra.backend.base import BaseBackend
from bibra.backend.config import GlobalLLMConfig, parse_bool_or_str, parse_int_or_str
from bibra.pages import (
    DEFAULT_PAGES,
    MAX_PAGES,
    parse_page_spec,
    resolve_page_indices,
)
from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)


BoolStr = Annotated[bool, BeforeValidator(parse_bool_or_str)]
IntStr = Annotated[int, BeforeValidator(parse_int_or_str)]


def _parse_pages(v: Any) -> list[int]:
    """Coerce a pages setting (list or spec string) to 1-based page numbers."""
    if isinstance(v, str):
        return parse_page_spec(v)
    return [int(p) for p in v]


PagesList = Annotated[list[int], BeforeValidator(_parse_pages)]


class NuExtractConfig(BaseModel):
    """Configuration for NuExtract backend."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(default="nuextract3", description="Model name")
    thinking: BoolStr = Field(default=False, description="Enable thinking mode")
    instructions: str = Field(default="", description="Custom instructions")
    dpi: IntStr = Field(default=170, ge=1, description="DPI for PDF rendering")
    pages: PagesList = Field(
        default=DEFAULT_PAGES,
        description=(
            "1-based page numbers to extract (negative from the end); "
            f"at most {MAX_PAGES} pages"
        ),
    )


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


def _pdf_pages_to_binary_content(
    pdf_path: str, dpi: int = 170, pages: list[int] | None = None
) -> list[BinaryContent]:
    """Render selected pages from a PDF as BinaryContent for pydantic_ai.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for page rendering.
        pages: Optional 1-based page numbers to render (negative counts
            from the last page). Defaults to first six + last two pages.

    Returns:
        List of BinaryContent objects with PNG data.
    """
    contents: list[BinaryContent] = []

    with pymupdf.open(pdf_path) as doc:
        valid_indices = resolve_page_indices(
            pages if pages is not None else DEFAULT_PAGES, len(doc)
        )

        for page_idx in valid_indices:
            pix = doc[page_idx].get_pixmap(dpi=dpi, alpha=False)
            contents.append(
                BinaryContent(data=pix.tobytes("png"), media_type="image/png")
            )

    return contents


class NuExtractBackend(BaseBackend[NuExtractConfig]):
    """Backend for metadata extraction using nuextract3 vision model."""

    cfg: NuExtractConfig

    def __init__(
        self,
        global_cfg: GlobalLLMConfig | None = None,
        cfg: NuExtractConfig | None = None,
    ):
        """Initialize the NuExtract backend.

        Args:
            global_cfg: Global LLM configuration. If None, uses defaults.
            cfg: NuExtract-specific configuration. If None, uses defaults.
        """
        self.global_cfg = global_cfg or GlobalLLMConfig()
        self.cfg = cfg or NuExtractConfig()

        api_key = self.global_cfg.api_key or "dummy-api-key"

        openai_client = AsyncOpenAI(
            base_url=self.global_cfg.endpoint_url,
            api_key=api_key,
            default_headers=self.global_cfg.extra_headers,
        )

        provider = OpenAIProvider(openai_client=openai_client)

        model = OpenAIChatModel(
            model_name=self.cfg.model,
            provider=provider,
        )

        self.agent = Agent(
            model,
            output_type=PublicationMetadata,
        )

    @classmethod
    def build_config(cls, project: Any) -> dict[str, Any]:
        """Build constructor kwargs from a ProjectConfig."""
        global_cfg = GlobalLLMConfig(
            endpoint_url=project.endpoint,
            api_key=project.api_key,
            extra_headers=project.extra_headers,
        )
        cfg = NuExtractConfig(**project.extra)
        return {"global_cfg": global_cfg, "cfg": cfg}

    async def extract(
        self, file_paths: list[str], pages: list[int] | None = None
    ) -> PublicationMetadata:
        """Extract publication metadata from a PDF file using vision.

        Args:
            file_paths: List of file paths. Only the first PDF is used.
            pages: Optional 1-based page numbers to render; overrides the
                configured pages.

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
                pdf_path, dpi=self.cfg.dpi, pages=pages or self.cfg.pages
            )
        except Exception:
            logger.exception("Failed to convert PDF to images: %s", pdf_path)
            return PublicationMetadata()

        if not image_contents:
            logger.warning("No pages extracted from PDF: %s", pdf_path)
            return PublicationMetadata()

        chat_template_kwargs: dict = {
            "template": json.dumps(NUEXTRACT_TEMPLATE, indent=4),
            "enable_thinking": self.cfg.thinking,
        }
        if self.cfg.instructions:
            chat_template_kwargs["instructions"] = self.cfg.instructions

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
