"""Tests for the GreyLitLM backend module."""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import UnexpectedModelBehavior

from bibra.backend.config import GlobalLLMConfig, GreyLitLMConfig
from bibra.backend.greylitlm import GreyLitLMBackend
from bibra.types import PublicationMetadata

TEST_PDF_PATH = os.path.join(
    os.path.dirname(__file__), "..", "cypress", "fixtures", "test-document.pdf"
)


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

    def __init__(self, parts: list[MockTextPart], **kwargs):
        self.parts = parts
        self.usage = kwargs.get("usage", MockRequestUsage())
        self.model_name = kwargs.get("model_name", "test-model")
        self.timestamp = kwargs.get(
            "timestamp",
            datetime(2026, 5, 6, 12, 3, 26, 843532, tzinfo=UTC),
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
        self.output = kwargs.get("output", None)


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
    backend.global_cfg = GlobalLLMConfig()
    backend.greylitlm_cfg = GreyLitLMConfig()
    backend._instructions = backend.greylitlm_cfg.instructions + "\n\n{}"
    backend.agent = mock_agent
    return backend


class TestGreyLitLMBackend:
    """Tests for the GreyLitLMBackend class."""

    def test_init_with_default_config(self):
        """Backend should init with default GlobalLLMConfig and GreyLitLMConfig."""
        backend = GreyLitLMBackend()
        assert backend.global_cfg is not None
        assert backend.greylitlm_cfg is not None
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
        mock_run_result = MockRunResult(response=mock_response, output=expected)

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
        mock_run_result = MockRunResult(response=mock_response, output=expected)

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
        mock_run_result = MockRunResult(response=mock_response, output=expected)

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
            response=mock_response, output=PublicationMetadata()
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
        mock_run_result = MockRunResult(response=mock_response, output=expected)

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

    def test_extract_successfully_processes_pdf_file(self):
        """Backend should successfully process a real PDF file."""
        # Mock the extract_content function to return sample content
        with patch("bibra.backend.greylitlm.extract_content") as mock_extract:
            mock_extract.return_value = {"text": "Sample PDF content"}

            # Mock the agent response
            metadata = {"language": "en", "title": "Test PDF Title"}
            json_string = json.dumps(metadata)
            mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
            expected = PublicationMetadata(**metadata)
            mock_run_result = MockRunResult(response=mock_response, output=expected)

            mock_agent = MagicMock()
            mock_agent.run = async_mock(mock_run_result)

            backend = create_backend_with_mock_agent(mock_agent)

            result = run_async(backend.extract, [TEST_PDF_PATH])

            assert result.language == "en"
            assert result.title == "Test PDF Title"
            mock_extract.assert_called_once()

    def test_extract_handles_pdf_extraction_failure(self):
        """Backend should handle errors when extract_content fails."""
        # Mock extract_content to raise an exception
        with patch("bibra.backend.greylitlm.extract_content") as mock_extract:
            mock_extract.side_effect = Exception("PDF parsing failed")

            # Mock the agent response
            metadata = {"language": "en", "title": "Fallback Title"}
            json_string = json.dumps(metadata)
            mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
            expected = PublicationMetadata(**metadata)
            mock_run_result = MockRunResult(response=mock_response, output=expected)

            mock_agent = MagicMock()
            mock_agent.run = async_mock(mock_run_result)

            backend = create_backend_with_mock_agent(mock_agent)

            result = run_async(backend.extract, [TEST_PDF_PATH])

            # Should still return a result, using fallback prompt
            assert result is not None

    def test_extract_uses_first_pdf_only(self):
        """Backend should only process the first PDF when multiple files given."""
        # Create temp files with different extensions
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf1:
            pdf1.write(b"pdf content 1")
            pdf1_path = pdf1.name

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf2:
            pdf2.write(b"pdf content 2")
            pdf2_path = pdf2.name

        try:
            with patch("bibra.backend.greylitlm.extract_content") as mock_extract:
                mock_extract.return_value = {"text": "First PDF content"}

                metadata = {"language": "en", "title": "First PDF Title"}
                json_string = json.dumps(metadata)
                mock_response = MockModelResponse(
                    parts=[MockTextPart(content=json_string)]
                )
                expected = PublicationMetadata(**metadata)
                mock_run_result = MockRunResult(response=mock_response, output=expected)

                mock_agent = MagicMock()
                mock_agent.run = async_mock(mock_run_result)

                backend = create_backend_with_mock_agent(mock_agent)

                result = run_async(backend.extract, [pdf1_path, pdf2_path])

                assert result.title == "First PDF Title"
                # Should only be called once for the first PDF
                mock_extract.assert_called_once()
        finally:
            os.unlink(pdf1_path)
            os.unlink(pdf2_path)

    def test_extract_returns_fallback_when_no_pdf(self):
        """Backend should handle case when no PDF files are provided."""
        # Create a temp non-PDF file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as txt:
            txt.write(b"text content")
            txt_path = txt.name

        try:
            # Mock extract_content to track if it's called
            with patch("bibra.backend.greylitlm.extract_content") as mock_extract:
                metadata = {"language": "en", "title": "No PDF Title"}
                json_string = json.dumps(metadata)
                mock_response = MockModelResponse(
                    parts=[MockTextPart(content=json_string)]
                )
                expected = PublicationMetadata(**metadata)
                mock_run_result = MockRunResult(response=mock_response, output=expected)

                mock_agent = MagicMock()
                mock_agent.run = async_mock(mock_run_result)

                backend = create_backend_with_mock_agent(mock_agent)

                result = run_async(backend.extract, [txt_path])

                # Should return a result with fallback content
                assert result is not None
                # extract_content should NOT be called since no PDF found
                mock_extract.assert_not_called()
        finally:
            os.unlink(txt_path)

    def test_extract_returns_fallback_when_empty_list(self):
        """Backend should handle case when an empty file list is provided."""
        with patch("bibra.backend.greylitlm.extract_content") as mock_extract:
            metadata = {"language": "en", "title": "Empty List Title"}
            json_string = json.dumps(metadata)
            mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
            expected = PublicationMetadata(**metadata)
            mock_run_result = MockRunResult(response=mock_response, output=expected)

            mock_agent = MagicMock()
            mock_agent.run = async_mock(mock_run_result)

            backend = create_backend_with_mock_agent(mock_agent)

            result = run_async(backend.extract, [])

            assert result is not None
            mock_extract.assert_not_called()


class TestGreyLitLMConfigEnvVars:
    """Tests for GreyLitLMConfig environment variable handling."""

    def test_system_prompt_from_env(self, monkeypatch):
        """Config reads GREYLITLM_SYSTEM_PROMPT from env."""
        monkeypatch.setenv(
            "GREYLITLM_SYSTEM_PROMPT",
            "Custom system prompt from env.",
        )
        cfg = GreyLitLMConfig()
        assert cfg.system_prompt == "Custom system prompt from env."

    def test_instructions_from_env(self, monkeypatch):
        """Config reads GREYLITLM_INSTRUCTIONS from env."""
        monkeypatch.setenv(
            "GREYLITLM_INSTRUCTIONS",
            "Custom instructions template: {}",
        )
        cfg = GreyLitLMConfig()
        assert cfg.instructions == "Custom instructions template: {}"

    def test_system_prompt_default_when_env_not_set(self, monkeypatch):
        """GreyLitLMConfig should use built-in default when env var is not set."""
        monkeypatch.delenv("GREYLITLM_SYSTEM_PROMPT", raising=False)
        cfg = GreyLitLMConfig()
        assert (
            cfg.system_prompt
            == "You are a skilled librarian specialized in meticulous cataloguing of"
            " digital documents."
        )

    def test_instructions_default_when_env_not_set(self, monkeypatch):
        """GreyLitLMConfig should use built-in default when env var is not set."""
        monkeypatch.delenv("GREYLITLM_INSTRUCTIONS", raising=False)
        cfg = GreyLitLMConfig()
        assert (
            cfg.instructions == "Extract metadata from this document. Return as JSON."
        )


class TestGreyLitLMConfigEmptyStrings:
    """Tests for empty-string override behavior with is None checks."""

    def test_system_prompt_empty_string_override(self, monkeypatch):
        """Config should accept empty string when explicitly provided."""
        monkeypatch.delenv("GREYLITLM_SYSTEM_PROMPT", raising=False)
        cfg = GreyLitLMConfig(system_prompt="")
        assert cfg.system_prompt == ""

    def test_instructions_empty_string_override(self, monkeypatch):
        """Config accepts empty string for instructions when provided."""
        monkeypatch.delenv("GREYLITLM_INSTRUCTIONS", raising=False)
        cfg = GreyLitLMConfig(instructions="")
        assert cfg.instructions == ""

    def test_model_empty_string_override(self, monkeypatch):
        """Config should accept empty string for model when explicitly provided."""
        cfg = GreyLitLMConfig(model="")
        assert cfg.model == ""


class TestGlobalLLMConfigEmptyStrings:
    """Tests for empty-string override behavior with GlobalLLMConfig."""

    def test_endpoint_url_empty_string(self, monkeypatch):
        """Config should accept empty string for endpoint_url."""
        monkeypatch.delenv("LLM_ENDPOINT_URL", raising=False)
        cfg = GlobalLLMConfig(endpoint_url="")
        assert cfg.endpoint_url == ""

    def test_api_key_empty_string(self, monkeypatch):
        """Config should accept empty string for api_key."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        cfg = GlobalLLMConfig(api_key="")
        assert cfg.api_key == ""
