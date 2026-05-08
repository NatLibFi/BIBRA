"""Tests for the GreyLitLM backend module."""

from pydantic_ai import UnexpectedModelBehavior
import asyncio
import json
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock

import pytest


from bibra.backend.greylitlm import GreyLitLMBackend
from bibra.backend.config import LLMConfig
from bibra.types import PublicationMetadata


class MockTextPart:
    """Mock TextPart from pydantic_ai."""

    def __init__(self, content: str):
        self.content = content


class MockRequestUsage:
    """Mock RequestUsage."""

    def __init__(self, input_tokens: int = 100, output_tokens: int = 200):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class MockModelResponse:
    """Mock ModelResponse from pydantic_ai."""

    def __init__(self, parts: List[MockTextPart], **kwargs):
        self.parts = parts
        self.usage = kwargs.get("usage", MockRequestUsage())
        self.model_name = kwargs.get("model_name", "test-model")
        self.timestamp = kwargs.get(
            "timestamp",
            datetime(2026, 5, 6, 12, 3, 26, 843532, tzinfo=timezone.utc),
        )
        self.provider_name = kwargs.get("provider_name", "openai")
        self.provider_url = kwargs.get("provider_url", "https://example.com/v1/")
        self.provider_details = kwargs.get("provider_details", {})
        self.provider_response_id = kwargs.get("provider_response_id", "test-id")
        self.finish_reason = kwargs.get("finish_reason", "stop")
        self.run_id = kwargs.get("run_id", "test-run-id")


class MockRunResult:
    """Mock run result from pydantic_ai Agent.run()."""

    def __init__(self, response: MockModelResponse, **kwargs):
        self.response = response
        self.data = kwargs.get("data", None)


def async_mock(return_value):
    """Create an async mock that returns the specified value."""

    async def inner(*args, **kwargs):
        return return_value

    return inner


def run_async(coro, *args, **kwargs):
    """Run an async coroutine."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro(*args, **kwargs))
    finally:
        loop.close()


def create_backend_with_mock_agent(mock_agent):
    """Create a GreyLitLMBackend instance with a pre-configured mock agent."""
    backend = GreyLitLMBackend.__new__(GreyLitLMBackend)
    backend.config = LLMConfig()
    backend.agent = mock_agent
    return backend


class TestGreyLitLMBackend:
    """Tests for the GreyLitLMBackend class."""

    def test_init_with_default_config(self):
        """Backend should initialize with default LLMConfig."""
        backend = GreyLitLMBackend()
        assert backend.config is not None
        assert backend.agent is not None

    def test_extract_returns_parsed_metadata(self):
        """Backend should properly parse valid JSON response from LLM."""
        metadata = {
            "language": "fi",
            "title": "Kustannus- ja jakeluketjun vaiheet",
            "creator": ["Laitinen, Antti"],
            "year": "2024",
            "publisher": ["Suomen yliopistojen kirjatoimisto"],
            "e-isbn": ["9789527159751"],
            "type_coar": "research report",
        }
        json_string = json.dumps(metadata)

        mock_response = MockModelResponse(
            parts=[MockTextPart(content=json_string)],
            model_name="NatLibFi/gemma-3-4b-it-GreyLitLM-GGUF",
            provider_name="openai",
            provider_url="https://localhost:8000/v1/",
            provider_details={"finish_reason": "stop"},
            provider_response_id="chatcmpl-LRX5Pv0eNJ9LgNPKETf6ZCluil62YbKQ",
            finish_reason="stop",
            run_id="eb39170b-e7f3-4a16-bb90-350bc61053b0",
        )

        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, data=expected)

        # Create a mock agent
        mock_agent = MagicMock()
        mock_agent.run = async_mock(mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = run_async(backend.extract, [])

        assert isinstance(result, PublicationMetadata)
        assert result.language == "fi"
        assert result.title == "Kustannus- ja jakeluketjun vaiheet"
        assert result.creator == ["Laitinen, Antti"]
        assert result.year == "2024"
        assert result.publisher == ["Suomen yliopistojen kirjatoimisto"]
        assert result.e_isbn == ["9789527159751"]
        assert result.type_coar == "research report"
        assert result.doi is None
        assert result.p_isbn == []

    def test_extract_raises_on_invalid_json(self):
        """Backend should raise an error when LLM returns invalid JSON."""
        # With structured output (output_type=PublicationMetadata), pydantic_ai
        # will raise a ValidationError if it cannot parse the response.

        async def raise_error(*args, **kwargs):
            raise UnexpectedModelBehavior("Failed to parse response")

        mock_agent = MagicMock()
        mock_agent.run = raise_error
        backend = create_backend_with_mock_agent(mock_agent)

        with pytest.raises(UnexpectedModelBehavior):
            run_async(backend.extract, [])

    def test_extract_handles_multiple_text_parts(self):
        """Backend should extract content from the first TextPart it finds."""
        metadata = {
            "language": "en",
            "title": "Test Title",
        }
        json_string = json.dumps(metadata)

        mock_response = MockModelResponse(
            parts=[
                MockTextPart(content=json_string),
                MockTextPart(content="more ignored"),
            ],
        )
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, data=expected)

        mock_agent = MagicMock()
        mock_agent.run = async_mock(mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = run_async(backend.extract, [])

        assert result.language == "en"
        assert result.title == "Test Title"

    def test_extract_handles_response_without_parts_attribute(self):
        """Backend should fall back to str() when response has no 'parts'."""
        mock_response = MagicMock()
        del mock_response.parts
        mock_response.__str__ = lambda self: (
            '{"language": "sv", "title": "Fallback Test"}'
        )

        expected = PublicationMetadata(language="sv", title="Fallback Test")
        mock_run_result = MockRunResult(response=mock_response, data=expected)

        mock_agent = MagicMock()
        mock_agent.run = async_mock(mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = run_async(backend.extract, [])

        assert result.language == "sv"
        assert result.title == "Fallback Test"

    def test_extract_with_empty_parts_list(self):
        """Backend should return empty metadata when parts list is empty."""
        mock_response = MockModelResponse(parts=[])
        mock_run_result = MockRunResult(
            response=mock_response, data=PublicationMetadata()
        )

        mock_agent = MagicMock()
        mock_agent.run = async_mock(mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = run_async(backend.extract, [])

        assert isinstance(result, PublicationMetadata)
        assert result.language is None

    def test_extract_preserves_optional_fields(self):
        """Backend should correctly handle all optional metadata fields."""
        metadata = {
            "language": "de",
            "title": "Titel auf Deutsch",
            "alt_title": "Title in English",
            "creator": ["Müller, Hans", "Schmidt, Anna"],
            "year": "2023",
            "publisher": ["Deutscher Verlag"],
            "doi": "10.1234/example.doi",
            "e-isbn": ["978-3-16-148410-0"],
            "p-isbn": ["978-3-16-148410-1"],
            "e-issn": "1234-5678",
            "p-issn": "8765-4321",
            "type_coar": "journal article",
        }
        json_string = json.dumps(metadata)

        mock_response = MockModelResponse(
            parts=[MockTextPart(content=json_string)],
        )
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, data=expected)

        mock_agent = MagicMock()
        mock_agent.run = async_mock(mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = run_async(backend.extract, [])

        assert result.language == "de"
        assert result.title == "Titel auf Deutsch"
        assert result.alt_title == "Title in English"
        assert result.creator == ["Müller, Hans", "Schmidt, Anna"]
        assert result.year == "2023"
        assert result.publisher == ["Deutscher Verlag"]
        assert result.doi == "10.1234/example.doi"
        assert result.e_isbn == ["978-3-16-148410-0"]
        assert result.p_isbn == ["978-3-16-148410-1"]
        assert result.e_issn == "1234-5678"
        assert result.p_issn == "8765-4321"
        assert result.type_coar == "journal article"
