from typing import List

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from bibra.backend.config import LLMConfig
from bibra.types import PublicationMetadata


class GreylitLMBackend:
    """Backend implementation using GreylitLM (fine-tuned LLM) for metadata extraction."""

    def __init__(self, config: LLMConfig | None = None):
        """Initialize the GreylitLM backend.

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
            model_name="gpt-4o",
            provider=provider,
        )

        # Create the agent with the model, system prompt, and output type
        self.agent = Agent(
            model,
            instructions=self.config.SYSTEM_PROMPT,
            output_type=PublicationMetadata,
        )

    async def extract(self, files: List) -> PublicationMetadata:
        """Extract publication metadata from files.

        Args:
            files: List of files to process (currently accepts any files, text content is ignored).

        Returns:
            PublicationMetadata: Extracted metadata as JSON.
        """
        # Create a simple prompt with empty JSON as placeholder
        prompt_text = self.config.INSTRUCTION.format("{}")
        result = await self.agent.run(prompt_text)
        return result.data
