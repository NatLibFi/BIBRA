import logging
import tempfile
import os

from typing import List

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from bibra.backend.config import LLMConfig
from bibra.backend.pdf_extractor import extract_content
from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)


class GreyLitLMBackend:
    """Backend for metadata extraction using GreyLitLM (fine-tuned LLM)."""

    def __init__(self, config: LLMConfig | None = None):
        """Initialize the GreyLitLM backend.

        Args:
            config: LLM configuration. If None, uses default LLMConfig.
        """
        self.config = config or LLMConfig()

        # The OpenAI client requires an api_key even for custom endpoints
        # Use a dummy value if no API key is configured
        api_key = self.config.LLM_API_KEY or "dummy-api-key"

        # Create a custom OpenAI client with the configured base URL
        openai_client = AsyncOpenAI(
            base_url=self.config.LLM_ENDPOINT_URL,
            api_key=api_key,
        )

        # Create the OpenAI provider with the custom client
        provider = OpenAIProvider(openai_client=openai_client)

        # Create the model with the custom provider
        model = OpenAIChatModel(
            model_name=self.config.LLM_MODEL,
            provider=provider,
        )

        # Create the agent with the model, system prompt, and str output type.
        # We use str instead of PublicationMetadata because the fine-tuned model
        # returns JSON in a format that pydantic_ai's structured output parser
        # cannot reconcile with the schema. Manual parsing via Pydantic handles
        # aliases correctly.
        self.agent = Agent(
            model,
            instructions=self.config.SYSTEM_PROMPT,
            output_type=str,
        )

    async def extract(self, files: List) -> PublicationMetadata:
        """Extract publication metadata from files.

        Args:
            files: List of files to process. Only the first PDF is used.

        Returns:
            PublicationMetadata: Extracted metadata as JSON.
        """
        # Process only the first PDF file
        pdf_file = None
        for f in files:
            if f.filename and f.filename.lower().endswith(".pdf"):
                pdf_file = f
                break

        if pdf_file is None:
            logger.warning("No PDF file found in uploaded files")
            prompt_text = self.config.INSTRUCTION.format("No PDF content available.")
        else:
            # Save uploaded file to temporary location for pymupdf processing
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                content = await pdf_file.read()
                tmp.write(content)
                tmp_path = tmp.name

            try:
                # Extract PDF content (metadata + selected text chunks)
                content = extract_content(tmp_path)
                import json

                prompt_text = self.config.INSTRUCTION.format(
                    json.dumps(content, ensure_ascii=False, indent=2)
                )
            except Exception:
                logger.exception("Failed to extract PDF content: %s", tmp_path)
                prompt_text = self.config.INSTRUCTION.format(
                    "Failed to extract PDF content."
                )
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        result = await self.agent.run(prompt_text)
        logger.debug("Agent returned: %s", result.response)

        # Extract the text content from the response.
        # result.response is a ModelResponse with parts containing TextPart objects.
        text_content = None
        if hasattr(result.response, "parts"):
            for part in result.response.parts:
                if hasattr(part, "content"):
                    text_content = part.content
                    break
        if text_content is None:
            text_content = str(result.response)

        # Manually parse JSON using Pydantic (which respects aliases)
        try:
            return PublicationMetadata.model_validate_json(text_content)
        except Exception as e:
            logger.error("Failed to parse metadata JSON: %s", e)
            return PublicationMetadata()
