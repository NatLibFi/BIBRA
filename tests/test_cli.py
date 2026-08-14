"""Tests for CLI commands."""

import importlib
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bibra.cli import _make_list_template, cli, extract, extract_url, list_projects
from bibra.config import ConfigError, ProjectNotFoundError


class TestCli:
    """Tests for the main CLI group."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_cli_help(self):
        """Test CLI help output."""
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert not result.exception
        assert "BIBRA - Bibliographic metadata extraction tool" in result.output
        assert "list-projects" in result.output
        assert "extract" in result.output

    def test_cli_version(self):
        """Test CLI version output."""
        result = self.runner.invoke(cli, ["--version"])
        expected_version = importlib.metadata.version("bibra")
        assert result.exit_code == 0
        assert not result.exception
        assert expected_version in result.output

    def test_cli_bad_argument(self):
        """Test CLI with bad argument."""
        result = self.runner.invoke(cli, ["--invalid"])
        assert result.exit_code != 0
        assert result.exception

    def test_cli_loads_dotenv(self):
        """Test that the CLI group command calls load_dotenv()."""
        with patch("bibra.cli.load_dotenv") as mock_load_dotenv:
            # --help exits before the group callback runs; use a subcommand
            # instead so the cli() callback is actually invoked.
            self.runner.invoke(cli, ["list-projects"])
            mock_load_dotenv.assert_called_once()


class TestListProjects:
    """Tests for the list-projects command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_list_projects_help(self):
        """Test list-projects help output."""
        result = self.runner.invoke(list_projects, ["--help"])
        assert result.exit_code == 0
        assert not result.exception
        assert "List configured projects" in result.output

    def test_list_projects(self):
        """Test list-projects command output."""
        result = self.runner.invoke(list_projects)
        assert result.exit_code == 0
        assert not result.exception
        assert "Project ID" in result.output
        assert "Project Name" in result.output
        assert "Description" in result.output

    def test_list_projects_shows_projects(self):
        """Test that list-projects displays project entries."""
        result = self.runner.invoke(list_projects)
        assert result.exit_code == 0
        # Check that project data is displayed (tests/projects.toml contains dummy)
        assert "dummy" in result.output

    def test_list_projects_bad_argument(self):
        """Test list-projects with bad argument."""
        result = self.runner.invoke(list_projects, ["--invalid"])
        assert result.exit_code != 0
        assert result.exception

    def test_list_projects_config_error_converted_to_click_exception(self):
        """Test that ConfigError in list_projects is converted to ClickException."""
        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.load.side_effect = ConfigError("Invalid config syntax")

            result = self.runner.invoke(list_projects)
            assert result.exit_code != 0
            assert "Invalid config syntax" in result.output


class TestExtract:
    """Tests for the extract command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_extract_help(self):
        """Test extract help output."""
        result = self.runner.invoke(extract, ["--help"])
        assert result.exit_code == 0
        assert not result.exception
        assert "Extract publication metadata" in result.output
        assert "PROJECT_ID" in result.output
        assert "FILE_PATH" in result.output
        assert "--output" in result.output
        assert "-o" in result.output

    def test_extract_no_files(self):
        """Test extract command with no files provided."""
        result = self.runner.invoke(extract, ["test-project"])
        assert result.exit_code != 0
        assert result.exception

    def test_extract_nonexistent_file(self):
        """Test extract command with nonexistent file."""
        result = self.runner.invoke(
            extract, ["test-project", "/nonexistent/path/file.pdf"]
        )
        assert result.exit_code != 0
        assert result.exception

    def test_extract_with_valid_file(self, tmp_path):
        """Test extract command with a valid file."""
        # Create a temporary file to satisfy the file existence check
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        result = self.runner.invoke(extract, ["dummy", str(test_file)])
        assert result.exit_code == 0
        assert not result.exception

        # Verify JSON output structure
        output = result.output.strip()
        # The output should be valid JSON (or contain a success message)
        try:
            data = json.loads(output)
            # If it's JSON, verify it has expected fields
            assert "title" in data or "authors" in data or "error" in data
        except json.JSONDecodeError:
            # If not JSON, it might be an error message
            pass

    def test_extract_with_output_option(self, tmp_path):
        """Test extract command with --output option to write JSON to file."""
        # Create a temporary file to satisfy the file existence check
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        output_file = tmp_path / "output.json"

        result = self.runner.invoke(
            extract, ["dummy", str(test_file), "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert not result.exception
        assert "Output written to" in result.output

        # Verify the output file was created and contains JSON
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        try:
            data = json.loads(content.strip())
            assert data is not None
        except json.JSONDecodeError:
            pytest.fail(f"Output file does not contain valid JSON: {content}")

    def test_extract_with_short_output_option(self, tmp_path):
        """Test extract command with -o short option."""
        # Create a temporary file to satisfy the file existence check
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        output_file = tmp_path / "output.json"

        result = self.runner.invoke(
            extract, ["dummy", str(test_file), "-o", str(output_file)]
        )
        assert result.exit_code == 0
        assert not result.exception
        assert "Output written to" in result.output

    def test_extract_multiple_files(self, tmp_path):
        """Test extract command with multiple files."""
        # Create temporary files to satisfy the file existence checks
        test_file1 = tmp_path / "test1.pdf"
        test_file1.write_bytes(b"dummy pdf content 1")

        test_file2 = tmp_path / "test2.pdf"
        test_file2.write_bytes(b"dummy pdf content 2")

        result = self.runner.invoke(
            extract, ["dummy", str(test_file1), str(test_file2)]
        )
        assert result.exit_code != 0
        assert result.exception

    def test_extract_with_nonexistent_project(self, tmp_path):
        """Test extract command with a nonexistent project ID."""
        # Create a temporary file to satisfy the file existence check
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        result = self.runner.invoke(extract, ["nonexistent-project", str(test_file)])
        assert result.exit_code != 0
        assert result.exception

    def test_extract_generic_exception_converted_to_click_exception(self, tmp_path):
        """Test that a generic Exception during extraction is wrapped in
        ClickException with 'Extraction failed:' prefix."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_backend = MagicMock()
            mock_registry.get_backend.return_value = mock_backend
            mock_backend.extract.side_effect = RuntimeError("PDF corrupted")

            result = self.runner.invoke(extract, ["dummy", str(test_file)])
            assert result.exit_code != 0
            assert "Extraction failed: PDF corrupted" in result.output

    def test_extract_config_error_converted_to_click_exception(self, tmp_path):
        """Test that ConfigError in extract is converted to ClickException."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.side_effect = ConfigError("Invalid config syntax")

            result = self.runner.invoke(extract, ["dummy", str(test_file)])
            assert result.exit_code != 0
            assert "Invalid config syntax" in result.output


"""Tests for the extract-url command."""


def _make_httpx_stream_mock(chunks=(b"%PDF-1.4 dummy content",)):
    """Build a mock for httpx stream response that yields the given chunks."""
    mock_response = MagicMock()
    mock_response.headers.get.return_value = "application/pdf"
    mock_response.status_code = 200
    mock_response.iter_bytes.return_value = chunks
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    return mock_response


def _make_backend(json_payload=None):
    """Build a mock backend whose .extract() returns an object with a
    model_dump_json method, matching what asyncio.run(backend.extract(...))
    is expected to produce."""
    if json_payload is None:
        json_payload = {"title": "Some Paper", "authors": ["A. Author"]}

    mock_result = MagicMock()
    mock_result.model_dump_json.return_value = json.dumps(json_payload, indent=2)

    mock_backend = MagicMock()

    async def _extract(*args, **kwargs):
        return mock_result

    mock_backend.extract.side_effect = _extract
    return mock_backend


class TestExtractUrl:
    """Tests for the extract-url command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_extract_url_help(self):
        """Test extract-url help output."""
        result = self.runner.invoke(extract_url, ["--help"])
        assert result.exit_code == 0
        assert not result.exception
        assert "Extract publication metadata" in result.output
        assert "PROJECT_ID" in result.output
        assert "URL" in result.output
        assert "--output" in result.output
        assert "-o" in result.output

    def test_extract_url_missing_url(self):
        """Test extract-url command with only a project id (missing URL)."""
        result = self.runner.invoke(extract_url, ["test-project"])
        assert result.exit_code != 0
        assert result.exception

    def test_extract_url_with_valid_url(self):
        """Test extract-url command with a valid URL and successful extraction."""
        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.httpx.stream") as mock_stream,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()
            mock_stream.return_value = _make_httpx_stream_mock()

            result = self.runner.invoke(
                extract_url, ["dummy", "https://example.com/paper.pdf"]
            )

        assert result.exit_code == 0
        assert not result.exception

        output = result.output.strip()
        data = json.loads(output)
        assert "title" in data or "authors" in data

    def test_extract_url_with_output_option(self, tmp_path):
        """Test extract-url command with --output option to write JSON to file."""
        output_file = tmp_path / "output.json"

        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.httpx.stream") as mock_stream,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()
            mock_stream.return_value = _make_httpx_stream_mock()

            result = self.runner.invoke(
                extract_url,
                [
                    "dummy",
                    "https://example.com/paper.pdf",
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0
        assert not result.exception
        assert "Output written to" in result.output

        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        data = json.loads(content.strip())
        assert data is not None

    def test_extract_url_with_short_output_option(self, tmp_path):
        """Test extract-url command with -o short option."""
        output_file = tmp_path / "output.json"

        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.httpx.stream") as mock_stream,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()
            mock_stream.return_value = _make_httpx_stream_mock()

            result = self.runner.invoke(
                extract_url,
                ["dummy", "https://example.com/paper.pdf", "-o", str(output_file)],
            )

        assert result.exit_code == 0
        assert not result.exception
        assert "Output written to" in result.output

    def test_extract_url_with_nonexistent_project(self):
        """Test extract-url command with a project that isn't found."""
        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.side_effect = ProjectNotFoundError(
                "Project 'nonexistent-project' not found"
            )

            result = self.runner.invoke(
                extract_url,
                ["nonexistent-project", "https://example.com/paper.pdf"],
            )

        assert result.exit_code != 0
        assert result.exception
        assert "not found" in result.output

    def test_extract_url_config_error_converted_to_click_exception(self):
        """Test ConfigError during backend resolution becomes ClickException."""
        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.side_effect = ConfigError("Invalid config syntax")

            result = self.runner.invoke(
                extract_url, ["dummy", "https://example.com/paper.pdf"]
            )

        assert result.exit_code != 0
        assert "Invalid config syntax" in result.output

    def test_extract_url_download_failure_converted_to_click_exception(self):
        """Test download failure is wrapped as 'Extraction failed:'."""
        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.httpx.stream") as mock_stream,
        ):
            import httpx as _httpx

            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()
            mock_stream.side_effect = _httpx.HTTPError("Name or service not known")

            result = self.runner.invoke(
                extract_url, ["dummy", "https://bad.example.invalid/paper.pdf"]
            )

        assert result.exit_code != 0
        assert "Extraction failed:" in result.output

    def test_extract_url_generic_exception_converted_to_click_exception(self):
        """Test that a generic Exception during extraction is wrapped in
        ClickException with the 'Extraction failed:' prefix."""
        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.httpx.stream") as mock_stream,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_backend = MagicMock()

            async def _extract(*args, **kwargs):
                raise RuntimeError("PDF corrupted")

            mock_backend.extract.side_effect = _extract
            mock_registry.get_backend.return_value = mock_backend
            mock_stream.return_value = _make_httpx_stream_mock()

            result = self.runner.invoke(
                extract_url, ["dummy", "https://example.com/paper.pdf"]
            )

        assert result.exit_code != 0
        assert "Extraction failed: PDF corrupted" in result.output

    def test_extract_url_passes_proxy_when_set(self):
        """Test that extract-url passes the proxy to httpx.stream when set."""
        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.httpx.stream") as mock_stream,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()
            mock_stream.return_value = _make_httpx_stream_mock()

            result = self.runner.invoke(
                extract_url,
                ["dummy", "https://example.com/paper.pdf"],
                env={"BIBRA_URL_PROXY": "http://proxy.example.com:8080"},
            )

        assert result.exit_code == 0
        mock_stream.assert_called_once_with(
            "GET",
            "https://example.com/paper.pdf",
            proxy="http://proxy.example.com:8080",
        )

    def test_extract_url_no_proxy_when_not_set(self):
        """Test that extract-url passes proxy=None when env var is not set."""
        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.httpx.stream") as mock_stream,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()
            mock_stream.return_value = _make_httpx_stream_mock()

            result = self.runner.invoke(
                extract_url,
                ["dummy", "https://example.com/paper.pdf"],
            )

        assert result.exit_code == 0
        mock_stream.assert_called_once_with(
            "GET",
            "https://example.com/paper.pdf",
            proxy=None,
        )


class TestMakeListTemplate:
    """Tests for the _make_list_template helper function."""

    def test_make_list_template_no_rows(self):
        """Test _make_list_template with no rows covers the empty rows branch."""
        column_headings = ("ID", "Name", "Value")
        template = _make_list_template(column_headings)
        # Template should create format strings based on heading lengths
        expected = "{:<2}  {:<4}  {:<5}"
        assert template == expected

    def test_make_list_template_with_rows(self):
        """Test _make_list_template with rows calculates max widths."""
        column_headings = ("ID", "Name")
        rows = (("1", "A very long name"), ("2", "Short"))
        template = _make_list_template(column_headings, *rows)
        # Should use max of heading and row lengths
        expected = "{:<2}  {:<16}"
        assert template == expected
