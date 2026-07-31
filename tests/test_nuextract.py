"""Tests for the NuExtract backend module."""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from pydantic_ai import UnexpectedModelBehavior

from bibra.backend.config import GlobalLLMConfig, NuExtractConfig
from bibra.backend.nuextract import NuExtractBackend
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
    """Create a NuExtractBackend instance with a pre-configured mock agent."""
    backend = NuExtractBackend.__new__(NuExtractBackend)
    backend.global_cfg = GlobalLLMConfig()
    backend.nuextract_cfg = NuExtractConfig()
    backend.agent = mock_agent
    return backend


class TestNuExtractBackend:
    """Tests for the NuExtractBackend class."""

    def test_init_with_default_config(self):
        """Backend should initialize with default LLMConfig."""
        backend = NuExtractBackend()
        assert backend.global_cfg is not None
        assert backend.nuextract_cfg is not None
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
            model_name="nuextract3",
            provider_name="openai",
            provider_url="https://example.com/v1/",
            provider_details={"finish_reason": "stop"},
            provider_response_id="chatcmpl-test",
            finish_reason="stop",
            run_id="test-run-id",
        )

        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_agent.run = async_mock(mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = run_async(backend.extract, [TEST_PDF_PATH])

        assert isinstance(result, PublicationMetadata)
        assert result.language == "fi"
        assert result.title == "Kustannus- ja jakeluketjun vaiheet"
        assert result.creator == ["Laitinen, Antti"]
        assert result.year == "2024"
        assert result.publisher == ["Suomen yliopistojen kirjatoimisto"]
        assert result.e_isbn == ["9789527159751"]
        assert result.type_coar == "research report"

    def test_extract_raises_on_invalid_json(self):
        """Backend should return empty metadata when LLM fails with an exception."""

        async def raise_error(*args, **kwargs):
            raise UnexpectedModelBehavior("Failed to parse response")

        mock_agent = MagicMock()
        mock_agent.run = raise_error
        backend = create_backend_with_mock_agent(mock_agent)

        # Exception is caught and logged; returns empty metadata as fallback
        result = run_async(backend.extract, [TEST_PDF_PATH])
        assert result is not None
        assert result.title is None

    def test_extract_handles_empty_file_list(self):
        """Backend should return empty metadata when no files provided."""
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
        # No PDF files provided, so empty metadata is returned
        assert result.title is None

    def test_extract_handles_no_pdf_file(self):
        """Backend should return empty metadata when no PDF is found."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as txt:
            txt.write(b"text content")
            txt_path = txt.name

        try:
            metadata = {"language": "en", "title": "No PDF Title"}
            json_string = json.dumps(metadata)
            mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
            expected = PublicationMetadata(**metadata)
            mock_run_result = MockRunResult(response=mock_response, output=expected)

            mock_agent = MagicMock()
            mock_agent.run = async_mock(mock_run_result)

            backend = create_backend_with_mock_agent(mock_agent)

            result = run_async(backend.extract, [txt_path])

            assert result is not None
            # No PDF file found, so empty metadata is returned
            assert result.title is None
        finally:
            os.unlink(txt_path)

    def test_extract_handles_pdf_conversion_failure(self):
        """Backend should handle errors when PDF conversion fails."""
        metadata = {"language": "en", "title": "Fallback Title"}
        json_string = json.dumps(metadata)
        mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_agent.run = async_mock(mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = run_async(backend.extract, ["/nonexistent/path.pdf"])

        # Should return empty metadata on failure
        assert result is not None

    def test_extract_preserves_all_fields(self):
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

        mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_agent.run = async_mock(mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = run_async(backend.extract, [TEST_PDF_PATH])

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

    def test_extract_with_instructions_passes_instructions(self):
        """Backend should pass instructions when NUEXTRACT_INSTRUCTIONS is set."""

        metadata = {"language": "en", "title": "Test Title"}
        json_string = json.dumps(metadata)
        mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_run = MagicMock(return_value=async_mock(mock_run_result))
        mock_agent.run = mock_run

        backend = create_backend_with_mock_agent(mock_agent)

        backend.nuextract_cfg = NuExtractConfig(instructions="Custom instructions")

        run_async(backend.extract, [TEST_PDF_PATH])

        # Verify that run was called with instructions in chat_template_kwargs
        call_kwargs = mock_run.call_args[1]
        extra_body = call_kwargs["model_settings"]["extra_body"]
        chat_template = extra_body["chat_template_kwargs"]
        assert "instructions" in chat_template
        assert chat_template["instructions"] == "Custom instructions"

    def test_extract_without_instructions_omits_instructions(self):
        """Backend should not pass instructions when NUEXTRACT_INSTRUCTIONS is empty."""

        metadata = {"language": "en", "title": "Test Title"}
        json_string = json.dumps(metadata)
        mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_run = MagicMock(return_value=async_mock(mock_run_result))
        mock_agent.run = mock_run

        backend = create_backend_with_mock_agent(mock_agent)

        # Instructions are handled via config, no need to patch
        backend.nuextract_cfg = NuExtractConfig(instructions="")

        run_async(backend.extract, [TEST_PDF_PATH])

        # Verify that run was called without instructions in chat_template_kwargs
        call_kwargs = mock_run.call_args[1]
        extra_body = call_kwargs["model_settings"]["extra_body"]
        chat_template = extra_body["chat_template_kwargs"]
        assert "instructions" not in chat_template


class TestPdfPagesToBinaryContent:
    """Tests for the _pdf_pages_to_binary_content helper function."""

    def test_converts_pdf_to_binary_content(self):
        """Should convert PDF pages to BinaryContent objects."""
        from bibra.backend.nuextract import _pdf_pages_to_binary_content

        with patch("pymupdf.open") as mock_open:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_pix = MagicMock()
            mock_pix.tobytes.return_value = b"fake_png_data"
            mock_page.get_pixmap.return_value = mock_pix
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
            mock_doc.__len__ = MagicMock(return_value=1)
            mock_doc.__getitem__ = MagicMock(
                side_effect=lambda idx: mock_page if idx in (0, -1) else None
            )
            mock_open.return_value = mock_doc

            contents = _pdf_pages_to_binary_content("/fake/path.pdf")

            assert len(contents) == 1
            assert contents[0].media_type == "image/png"
            assert contents[0].data == b"fake_png_data"
            mock_page.get_pixmap.assert_called_once_with(dpi=170, alpha=False)

    def test_handles_empty_pdf(self):
        """Should return empty list for PDF with no pages."""
        from bibra.backend.nuextract import _pdf_pages_to_binary_content

        with patch("pymupdf.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_doc.__len__ = MagicMock(return_value=0)
            mock_open.return_value = mock_doc

            contents = _pdf_pages_to_binary_content("/fake/path.pdf")

            assert contents == []

    def test_uses_custom_dpi(self):
        """Should respect custom DPI parameter."""
        from bibra.backend.nuextract import _pdf_pages_to_binary_content

        with patch("pymupdf.open") as mock_open:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_pix = MagicMock()
            mock_pix.tobytes.return_value = b"fake_png_data"
            mock_page.get_pixmap.return_value = mock_pix
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
            mock_doc.__len__ = MagicMock(return_value=1)
            mock_doc.__getitem__ = MagicMock(
                side_effect=lambda idx: mock_page if idx in (0, -1) else None
            )
            mock_open.return_value = mock_doc

            _pdf_pages_to_binary_content("/fake/path.pdf", dpi=300)

            mock_page.get_pixmap.assert_called_once_with(dpi=300, alpha=False)
