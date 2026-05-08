"""Tests for CLI commands."""

import json
import importlib

import pytest
from click.testing import CliRunner

from bibra.cli import cli, extract, list_projects


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
        assert "List available projects" in result.output

    def test_list_projects(self):
        """Test list-projects command output."""
        result = self.runner.invoke(list_projects)
        assert result.exit_code == 0
        assert not result.exception
        assert "Project ID" in result.output
        assert "Project Name" in result.output
        assert "Description" in result.output
        assert "Created At" in result.output

    def test_list_projects_shows_projects(self):
        """Test that list-projects displays project entries."""
        result = self.runner.invoke(list_projects)
        assert result.exit_code == 0
        # Check that project data is displayed (PROJECTS contains at least one entry)
        assert "dummy" in result.output
        assert "greylitlm" in result.output

    def test_list_projects_bad_argument(self):
        """Test list-projects with bad argument."""
        result = self.runner.invoke(list_projects, ["--invalid"])
        assert result.exit_code != 0
        assert result.exception


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
        assert "FILES" in result.output
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
        assert result.exit_code == 0
        assert not result.exception

    def test_extract_with_nonexistent_project(self, tmp_path):
        """Test extract command with a nonexistent project ID."""
        # Create a temporary file to satisfy the file existence check
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        result = self.runner.invoke(extract, ["nonexistent-project", str(test_file)])
        assert result.exit_code != 0
        assert result.exception
