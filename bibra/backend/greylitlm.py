"""Backend for metadata extraction from grey literature using fine-tuned LLMs."""

import json
import logging
from pathlib import Path

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from bibra.backend.config import GlobalLLMConfig, GreyLitLMConfig
from bibra.backend.pdf_extractor import extract_content
from bibra.types import PublicationMetadata

logger = logging.getLogger(__name__)


class GreyLitLMBackend:
    """Backend for metadata extraction using GreyLitLM (fine-tuned LLM)."""

    def __init__(
        self,
        global_cfg: GlobalLLMConfig | None = None,
        greylitlm_cfg: GreyLitLMConfig | None = None,
    ):
        """Initialize the GreyLitLM backend.

        Args:
            global_cfg: Global LLM configuration. If None, uses defaults.
            greylitlm_cfg: GreylitLM-specific configuration. If None, uses defaults.
        """
        self.global_cfg = global_cfg or GlobalLLMConfig()
        self.greylitlm_cfg = greylitlm_cfg or GreyLitLMConfig()

        # The OpenAI client requires an api_key even for custom endpoints
        # Use a dummy value if no API key is configured
        api_key = self.global_cfg.api_key or "dummy-api-key"

        # Create a custom OpenAI client with the configured base URL
        openai_client = AsyncOpenAI(
            base_url=self.global_cfg.endpoint_url,
            api_key=api_key,
        )

        # Create the OpenAI provider with the custom client
        provider = OpenAIProvider(openai_client=openai_client)

        # Create the model with the custom provider
        model = OpenAIChatModel(
            model_name=self.greylitlm_cfg.model,
            provider=provider,
        )

        # Create the agent with the model and structured output.
        # Using PublicationMetadata directly lets pydantic_ai parse the JSON
        # response into the model, handling aliases via populate_by_name=True.
        self.agent = Agent(
            model,
            instructions=self.greylitlm_cfg.system_prompt,
            output_type=PublicationMetadata,
        )

    async def extract(self, file_paths: list[str]) -> PublicationMetadata:
        """Extract publication metadata from files.

        Args:
            file_paths: List of file paths to process. Only the first PDF is used.

        Returns:
            PublicationMetadata: Extracted metadata as JSON.
        """
        # Process only the first PDF file
        pdf_path = None
        for path in file_paths:
            if Path(path).suffix.lower() == ".pdf":
                pdf_path = path
                break

        if pdf_path is None:
            logger.warning("No PDF file found in uploaded files")
            prompt_text = self.greylitlm_cfg.instructions.format(
                "No PDF content available."
            )
        else:
            try:
                content = extract_content(pdf_path)
                prompt_text = self.greylitlm_cfg.instructions.format(
                    json.dumps(content, ensure_ascii=False, indent=2)
                )
            except Exception:
                logger.exception("Failed to extract PDF content: %s", pdf_path)
                prompt_text = self.greylitlm_cfg.instructions.format(
                    "Failed to extract PDF content."
                )

        result = await self.agent.run(prompt_text)
        logger.debug("Agent returned: %s", result.response)
        return result.output
