"""Tests for the NuExtract backend module."""

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import UnexpectedModelBehavior

from bibra.backend.config import GlobalLLMConfig
from bibra.backend.nuextract import (
    NuExtractBackend,
    NuExtractConfig,
    _parse_bool_or_str,
    _parse_int_or_str,
)
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


def create_backend_with_mock_agent(mock_agent):
    """Create a NuExtractBackend instance with a pre-configured mock agent."""
    backend = NuExtractBackend.__new__(NuExtractBackend)
    backend.global_cfg = GlobalLLMConfig()
    backend.cfg = NuExtractConfig()
    backend.agent = mock_agent
    return backend


class TestNuExtractBackend:
    """Tests for the NuExtractBackend class."""

    def test_init_with_default_config(self):
        """Backend should init with default GlobalLLMConfig and NuExtractConfig."""
        backend = NuExtractBackend()
        assert backend.global_cfg is not None
        assert backend.cfg is not None
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
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = asyncio.run(backend.extract([TEST_PDF_PATH]))

        assert isinstance(result, PublicationMetadata)
        assert result.language == "fi"
        assert result.title == "Kustannus- ja jakeluketjun vaiheet"
        assert result.creator == ["Laitinen, Antti"]
        assert result.year == "2024"
        assert result.publisher == ["Suomen yliopistojen kirjatoimisto"]
        assert result.e_isbn == ["9789527159751"]
        assert result.type_coar == "research report"

    def test_extract_raises_on_llm_exception(self):
        """Backend should raise exception when LLM fails."""

        async def raise_error(*args, **kwargs):
            raise UnexpectedModelBehavior("Failed to parse response")

        mock_agent = MagicMock()
        mock_agent.run = raise_error
        backend = create_backend_with_mock_agent(mock_agent)

        with (
            patch(
                "bibra.backend.nuextract._pdf_pages_to_binary_content",
                return_value=[MagicMock(media_type="image/png", data=b"fake")],
            ),
            pytest.raises(UnexpectedModelBehavior),
        ):
            asyncio.run(backend.extract([TEST_PDF_PATH]))

    def test_extract_handles_empty_file_list(self):
        """Backend should return empty metadata when no files provided."""
        metadata = {"language": "en", "title": "Empty List Title"}
        json_string = json.dumps(metadata)
        mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        result = asyncio.run(backend.extract([]))

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
            mock_agent.run = AsyncMock(return_value=mock_run_result)

            backend = create_backend_with_mock_agent(mock_agent)

            result = asyncio.run(backend.extract([txt_path]))

            assert result is not None
            # No PDF file found, so empty metadata is returned
            assert result.title is None
        finally:
            os.unlink(txt_path)

    def test_extract_handles_pdf_conversion_failure(self):
        """Backend should handle errors when PDF conversion fails."""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock()

        backend = create_backend_with_mock_agent(mock_agent)

        result = asyncio.run(backend.extract(["/nonexistent/path.pdf"]))

        # Should return empty metadata on failure
        assert result is not None
        assert result.title is None
        mock_agent.run.assert_not_called()

    def test_extract_handles_empty_pdf_pages(self):
        """Backend should return empty metadata when PDF has no extractable pages."""
        metadata = {"language": "en", "title": "Should Not Appear"}
        json_string = json.dumps(metadata)
        mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        with patch(
            "bibra.backend.nuextract._pdf_pages_to_binary_content", return_value=[]
        ):
            result = asyncio.run(backend.extract([TEST_PDF_PATH]))

        assert result is not None
        assert result.title is None
        mock_agent.run.assert_not_called()

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
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        with patch(
            "bibra.backend.nuextract._pdf_pages_to_binary_content",
            return_value=[MagicMock(media_type="image/png", data=b"fake")],
        ):
            result = asyncio.run(backend.extract([TEST_PDF_PATH]))

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
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        backend.cfg = NuExtractConfig(instructions="Custom instructions")

        with patch(
            "bibra.backend.nuextract._pdf_pages_to_binary_content",
            return_value=[MagicMock(media_type="image/png", data=b"fake")],
        ):
            asyncio.run(backend.extract([TEST_PDF_PATH]))

        # Verify that run was called with instructions in chat_template_kwargs
        call_kwargs = mock_agent.run.call_args[1]
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
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        # Instructions are handled via config, no need to patch
        backend.cfg = NuExtractConfig(instructions="")

        with patch(
            "bibra.backend.nuextract._pdf_pages_to_binary_content",
            return_value=[MagicMock(media_type="image/png", data=b"fake")],
        ):
            asyncio.run(backend.extract([TEST_PDF_PATH]))

        # Verify that run was called without instructions in chat_template_kwargs
        call_kwargs = mock_agent.run.call_args[1]
        extra_body = call_kwargs["model_settings"]["extra_body"]
        chat_template = extra_body["chat_template_kwargs"]
        assert "instructions" not in chat_template

    def test_extract_with_thinking_sets_enable_thinking(self):
        """Backend should set enable_thinking=True when thinking=True."""

        metadata = {"language": "en", "title": "Test Title"}
        json_string = json.dumps(metadata)
        mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        backend.cfg = NuExtractConfig(thinking=True)

        with patch(
            "bibra.backend.nuextract._pdf_pages_to_binary_content",
            return_value=[MagicMock(media_type="image/png", data=b"fake")],
        ):
            asyncio.run(backend.extract([TEST_PDF_PATH]))

        # Verify that run was called with enable_thinking=True in chat_template_kwargs
        call_kwargs = mock_agent.run.call_args[1]
        extra_body = call_kwargs["model_settings"]["extra_body"]
        chat_template = extra_body["chat_template_kwargs"]
        assert chat_template["enable_thinking"] is True

    def test_extract_without_thinking_sets_enable_thinking_false(self):
        """Backend should set enable_thinking=False when thinking=False."""

        metadata = {"language": "en", "title": "Test Title"}
        json_string = json.dumps(metadata)
        mock_response = MockModelResponse(parts=[MockTextPart(content=json_string)])
        expected = PublicationMetadata(**metadata)
        mock_run_result = MockRunResult(response=mock_response, output=expected)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        backend = create_backend_with_mock_agent(mock_agent)

        backend.cfg = NuExtractConfig(thinking=False)

        with patch(
            "bibra.backend.nuextract._pdf_pages_to_binary_content",
            return_value=[MagicMock(media_type="image/png", data=b"fake")],
        ):
            asyncio.run(backend.extract([TEST_PDF_PATH]))

        # Verify that run was called with enable_thinking=False in chat_template_kwargs
        call_kwargs = mock_agent.run.call_args[1]
        extra_body = call_kwargs["model_settings"]["extra_body"]
        chat_template = extra_body["chat_template_kwargs"]
        assert chat_template["enable_thinking"] is False


class TestNuExtractConfigEmptyStrings:
    """Tests for empty-string override behavior with NuExtractConfig."""

    def test_model_empty_string_override(self, monkeypatch):
        """Config should accept empty string for model when explicitly provided."""
        monkeypatch.delenv("NUEXTRACT_MODEL", raising=False)
        cfg = NuExtractConfig(model="")
        assert cfg.model == ""

    def test_dpi_default(self, monkeypatch):
        """Config should default DPI to 170 when env var not set."""
        monkeypatch.delenv("NUEXTRACT_DPI", raising=False)
        cfg = NuExtractConfig()
        assert cfg.dpi == 170

    def test_dpi_explicit(self):
        """Config should accept explicit DPI value."""
        cfg = NuExtractConfig(dpi=200)
        assert cfg.dpi == 200

    def test_instructions_empty_string_override(self, monkeypatch):
        """Config should accept empty string for instructions."""
        monkeypatch.delenv("NUEXTRACT_INSTRUCTIONS", raising=False)
        cfg = NuExtractConfig(instructions="")
        assert cfg.instructions == ""

    def test_dpi_empty_string(self, monkeypatch):
        """Config should default DPI to 170 when NUEXTRACT_DPI is empty string."""
        monkeypatch.setenv("NUEXTRACT_DPI", "")
        cfg = NuExtractConfig()
        assert cfg.dpi == 170

    def test_dpi_none_string(self, monkeypatch):
        """Config should default DPI to 170 when NUEXTRACT_DPI is 'none'."""
        monkeypatch.setenv("NUEXTRACT_DPI", "none")
        cfg = NuExtractConfig()
        assert cfg.dpi == 170

    def test_dpi_invalid_string(self, monkeypatch):
        """Config should default DPI to 170 when NUEXTRACT_DPI is non-numeric."""
        monkeypatch.setenv("NUEXTRACT_DPI", "abc")
        cfg = NuExtractConfig()
        assert cfg.dpi == 170

    def test_dpi_whitespace_only(self, monkeypatch):
        """Config should default DPI to 170 when NUEXTRACT_DPI is whitespace."""
        monkeypatch.setenv("NUEXTRACT_DPI", "  ")
        cfg = NuExtractConfig()
        assert cfg.dpi == 170

    def test_dpi_negative_value(self, monkeypatch):
        """Config should fall back to default DPI when NUEXTRACT_DPI is negative."""
        monkeypatch.setenv("NUEXTRACT_DPI", "-100")
        cfg = NuExtractConfig()
        assert cfg.dpi == 170

    def test_dpi_zero_value(self, monkeypatch):
        """Config should fall back to default DPI when NUEXTRACT_DPI is zero."""
        monkeypatch.setenv("NUEXTRACT_DPI", "0")
        cfg = NuExtractConfig()
        assert cfg.dpi == 170


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


class TestParseBoolOrStr:
    """Tests for _parse_bool_or_str validator."""

    def test_bool_true_passed_through(self):
        assert _parse_bool_or_str(True) is True

    def test_bool_false_passed_through(self):
        assert _parse_bool_or_str(False) is False

    def test_int_zero_returns_false(self):
        assert _parse_bool_or_str(0) is False

    def test_int_nonzero_returns_true(self):
        assert _parse_bool_or_str(1) is True

    def test_int_nonzero_negative_returns_true(self):
        assert _parse_bool_or_str(-1) is True

    def test_string_true_returns_true(self):
        assert _parse_bool_or_str("true") is True

    def test_string_1_returns_true(self):
        assert _parse_bool_or_str("1") is True

    def test_string_with_whitespace(self):
        assert _parse_bool_or_str("  true  ") is True

    def test_string_false_returns_false_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert _parse_bool_or_str("false") is False
        assert "Unrecognized bool value" in caplog.text
        assert "'false'" in caplog.text

    def test_string_yes_returns_false_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert _parse_bool_or_str("yes") is False
        assert "Unrecognized bool value" in caplog.text
        assert "'yes'" in caplog.text

    def test_string_maybe_returns_false_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert _parse_bool_or_str("maybe") is False
        assert "Unrecognized bool value" in caplog.text

    def test_string_2_returns_false_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert _parse_bool_or_str("2") is False
        assert "Unrecognized bool value" in caplog.text


class TestParseIntOrStr:
    """Tests for _parse_int_or_str validator."""

    def test_int_passed_through(self):
        assert _parse_int_or_str(42) == 42

    def test_string_number(self):
        assert _parse_int_or_str("42") == 42

    def test_string_negative_number(self):
        assert _parse_int_or_str("-5") == -5

    def test_string_with_whitespace(self):
        assert _parse_int_or_str("  10  ") == 10

    def test_string_invalid_returns_zero_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert _parse_int_or_str("abc") == 0
        assert "Unrecognized int value" in caplog.text
        assert "'abc'" in caplog.text

    def test_string_float_returns_zero_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert _parse_int_or_str("3.14") == 0
        assert "Unrecognized int value" in caplog.text

    def test_empty_string_returns_zero_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert _parse_int_or_str("") == 0
        assert "Unrecognized int value" in caplog.text

    def test_whitespace_only_returns_zero_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert _parse_int_or_str("   ") == 0
        assert "Unrecognized int value" in caplog.text
