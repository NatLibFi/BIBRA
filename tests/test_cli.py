"""Tests for CLI commands."""

import importlib
import importlib.metadata
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest
import yaml
from click.testing import CliRunner

from bibra.cli import (
    _make_list_template,
    cli,
    extract,
    extract_url,
    list_projects,
    serve,
)
from bibra.config import ConfigError, ProjectNotFoundError
from bibra.types import PublicationMetadata


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
        assert "serve" in result.output
        assert "eval" in result.output

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


@pytest.fixture
def eval_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """Create matching JSONL collections with one correct and one wrong field."""
    gt_path = tmp_path / "gold.jsonl"
    pred_path = tmp_path / "predictions.jsonl"
    for path, year in ((gt_path, "2026"), (pred_path, "2025")):
        path.write_text(
            json.dumps({"doc_id": "book-1", "record": {"title": "Book", "year": year}})
            + "\n",
            encoding="utf-8",
        )
    return gt_path, pred_path


def _assert_eval_summary(output: str, mode: str, value: float, support: float) -> None:
    """Check the displayed summary against independently expected scores."""
    expected = pl.DataFrame(
        {
            "metric": ["f1", "prec", "rec"],
            "mode": [mode] * 3,
            "value": [value] * 3,
            "support": [support] * 3,
        },
        schema_overrides={"support": pl.UInt32 if mode == "doc-avg" else pl.Float64},
    )
    assert output.strip() == str(expected)


class TestEvaluate:
    """Exercise the eval command against the real bibraeval API."""

    @pytest.mark.parametrize("mode", ["doc-avg", "field-avg", "micro-avg"])
    @pytest.mark.parametrize("input_format", ["jsonl", "directory"])
    def test_summary_and_exports(self, eval_inputs, tmp_path, mode, input_format):
        """Validate computed scores, table output and the mode-specific exports."""
        gt_path, pred_path = eval_inputs
        if input_format == "directory":
            directories = (tmp_path / "gold", tmp_path / "predictions")
            for file_path, directory in zip(eval_inputs, directories, strict=True):
                directory.mkdir()
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                (directory / "book-1.json").write_text(
                    json.dumps(payload["record"]), encoding="utf-8"
                )
            gt_path, pred_path = directories
        results_dir = tmp_path / "results" / mode
        result = CliRunner().invoke(
            cli,
            [
                "eval",
                "--ground-truth",
                str(gt_path),
                "--predictions",
                str(pred_path),
                "--mode",
                mode,
                "--results-dir",
                str(results_dir),
            ],
        )

        assert result.exit_code == 0, result.output
        support = {
            "doc-avg": 1,
            "field-avg": 2 / len(PublicationMetadata.model_fields),
            "micro-avg": 2,
        }[mode]
        _assert_eval_summary(result.output, mode, 0.5, support)
        summary = yaml.safe_load(
            (results_dir / "summary_metrics.yaml").read_text(encoding="utf-8")
        )
        assert set(summary) == {"prec", "rec", "f1"}
        for row in summary.values():
            assert set(row) == {"mode", "value", "support"}
            assert row["mode"] == mode
            assert row["value"] == pytest.approx(0.5)
            assert row["support"] == pytest.approx(support)
        comparison = (results_dir / "comparison_matrix.csv").read_text(encoding="utf-8")
        assert "cell_agreement" in comparison
        assert "book-1" in comparison
        assert (results_dir / "intermediate_results.csv").exists() == (
            mode != "micro-avg"
        )

    def test_defaults_and_no_export(self, eval_inputs, tmp_path):
        """Use Evaluator defaults without exporting files."""
        gt_path, pred_path = eval_inputs
        result = CliRunner().invoke(
            cli,
            ["eval", "--ground-truth", str(gt_path), "--predictions", str(pred_path)],
        )
        assert result.exit_code == 0, result.output
        _assert_eval_summary(
            result.output, "field-avg", 0.5, 2 / len(PublicationMetadata.model_fields)
        )
        assert {path.name for path in tmp_path.iterdir()} == {
            "gold.jsonl",
            "predictions.jsonl",
        }

    @pytest.mark.parametrize(
        ("option", "wrapped"),
        [("--field-metric-config", False), ("--field_metric_config", True)],
    )
    def test_custom_metrics(self, eval_inputs, tmp_path, option, wrapped):
        """Accept both config spellings and YAML layouts, applying fuzzy weights."""
        gt_path, pred_path = eval_inputs
        pred_path.write_text(
            json.dumps(
                {"doc_id": "book-1", "record": {"title": "Books", "year": "2025"}}
            ),
            encoding="utf-8",
        )
        config = tmp_path / "metrics.yaml"
        yaml_content = (
            "title:\n  metric: Levenshtein\n  match_threshold: 0.5\n  weight: 2\n"
            "year:\n  metric: Exact\n  weight: 1\n"
        )
        if wrapped:
            yaml_content = "fields:\n" + "".join(
                "  " + line + "\n" for line in yaml_content.splitlines()
            )
        config.write_text(yaml_content, encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            [
                "eval",
                "--ground-truth",
                str(gt_path),
                "--predictions",
                str(pred_path),
                option,
                str(config),
            ],
        )
        assert result.exit_code == 0, result.output
        _assert_eval_summary(result.output, "field-avg", 2 * (8 / 9) / 3, 1)

    def test_mismatched_ids_require_opt_in(self, eval_inputs):
        """Report mismatched IDs unless the caller explicitly drops them."""
        gt_path, pred_path = eval_inputs
        with gt_path.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps({"doc_id": "extra", "record": {"title": "Extra"}}) + "\n"
            )
        args = ["eval", "--ground-truth", str(gt_path), "--predictions", str(pred_path)]
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 1
        assert "Evaluation failed" in result.output
        assert "mismatched doc_ids" in result.output
        result = CliRunner().invoke(cli, [*args, "--drop-mismatched-doc-ids"])
        assert result.exit_code == 0, result.output
        _assert_eval_summary(
            result.output, "field-avg", 0.5, 2 / len(PublicationMetadata.model_fields)
        )

    @pytest.mark.parametrize(
        "content",
        [
            "{",
            '{"doc_id": "book-1"}',
            '{"doc_id": "book-1", "record": {"title": 123}}',
        ],
    )
    def test_invalid_records(self, eval_inputs, content):
        """Translate ingestion and schema validation failures into CLI errors."""
        gt_path, pred_path = eval_inputs
        pred_path.write_text(content, encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            ["eval", "--ground-truth", str(gt_path), "--predictions", str(pred_path)],
        )
        assert result.exit_code == 1
        assert "Error: Evaluation failed:" in result.output

    @pytest.mark.parametrize(
        "content", ["title: [", "- title", "title:\n  metric: unknown"]
    )
    def test_invalid_config(self, eval_inputs, tmp_path, content):
        """Report malformed YAML, non-mappings and unsupported metrics."""
        gt_path, pred_path = eval_inputs
        config = tmp_path / "metrics.yaml"
        config.write_text(content, encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            [
                "eval",
                "--ground-truth",
                str(gt_path),
                "--predictions",
                str(pred_path),
                "--field-metric-config",
                str(config),
            ],
        )
        assert result.exit_code == 1
        assert "Error: Evaluation failed:" in result.output

    @pytest.mark.parametrize(
        "args",
        [
            [],
            ["--ground-truth", "{gt}"],
            ["--ground-truth", "{gt}", "--predictions", "missing.jsonl"],
            ["--ground-truth", "{gt}", "--predictions", "{pred}", "--mode", "bad"],
        ],
    )
    def test_invalid_options(self, eval_inputs, args):
        """Reject missing inputs, nonexistent paths and unsupported modes."""
        gt_path, pred_path = eval_inputs
        result = CliRunner().invoke(
            cli,
            ["eval", *(arg.format(gt=gt_path, pred=pred_path) for arg in args)],
        )
        assert result.exit_code == 2
        assert "Error:" in result.output

    def test_export_error(self, eval_inputs):
        """Do not print a success summary when writing results fails."""
        gt_path, pred_path = eval_inputs
        with patch(
            "bibraeval.evaluator.Evaluator.save_results",
            side_effect=PermissionError("Cannot write results"),
        ):
            result = CliRunner().invoke(
                cli,
                [
                    "eval",
                    "--ground-truth",
                    str(gt_path),
                    "--predictions",
                    str(pred_path),
                    "--results-dir",
                    str(gt_path.parent / "results"),
                ],
            )
        assert result.exit_code == 1
        assert "Error: Evaluation failed: Cannot write results" in result.output


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

    def test_extract_pages_option_shown_in_help(self):
        """The --pages option should be documented in the help output."""
        result = self.runner.invoke(extract, ["--help"])
        assert result.exit_code == 0
        assert "--pages" in result.output

    def test_extract_with_pages_passes_parsed_pages(self, tmp_path):
        """--pages should be parsed and passed to the backend."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        captured = {}
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = "{}"

        async def _extract(*args, **kwargs):
            captured.update(kwargs)
            return mock_result

        mock_backend = MagicMock()
        mock_backend.extract.side_effect = _extract

        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = mock_backend

            result = self.runner.invoke(
                extract, ["dummy", str(test_file), "--pages", "1-4,-2--1"]
            )

        assert result.exit_code == 0
        assert captured["pages"] == [1, 2, 3, 4, -2, -1]

    def test_extract_without_pages_passes_none(self, tmp_path):
        """Without --pages, None should be passed to the backend."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        captured = {}
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = "{}"

        async def _extract(*args, **kwargs):
            captured.update(kwargs)
            return mock_result

        mock_backend = MagicMock()
        mock_backend.extract.side_effect = _extract

        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = mock_backend

            result = self.runner.invoke(extract, ["dummy", str(test_file)])

        assert result.exit_code == 0
        assert captured["pages"] is None

    def test_extract_with_invalid_pages(self, tmp_path):
        """An invalid --pages value should be a usage error."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

            result = self.runner.invoke(
                extract, ["dummy", str(test_file), "--pages", "1,a"]
            )

        assert result.exit_code != 0
        assert "Invalid page specification item" in result.output

    def test_extract_with_page_zero_is_usage_error(self, tmp_path):
        """--pages 0 is rejected with a usage error before any backend runs."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"dummy pdf content")

        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

            result = self.runner.invoke(
                extract, ["dummy", str(test_file), "--pages", "0"]
            )

        assert result.exit_code != 0
        assert "Page 0" in result.output


class TestServe:
    """Tests for the serve command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_serve_help(self):
        """Test serve help output."""
        result = self.runner.invoke(serve, ["--help"])
        assert result.exit_code == 0
        assert not result.exception
        assert "Serve the BIBRA API server" in result.output
        assert "--host" in result.output
        assert "--port" in result.output
        assert "-p" in result.output
        assert "--reload" in result.output

    def test_serve_defaults(self):
        """Test that serve calls uvicorn.run with default host and port."""
        with patch("bibra.cli.uvicorn.run") as mock_uvicorn_run:
            result = self.runner.invoke(serve)
            assert result.exit_code == 0
            assert not result.exception
            mock_uvicorn_run.assert_called_once_with(
                "bibra.main:app", host="127.0.0.1", port=8000, reload=False
            )

    def test_serve_with_options(self):
        """Test that serve passes host, port, and reload to uvicorn.run."""
        with patch("bibra.cli.uvicorn.run") as mock_uvicorn_run:
            result = self.runner.invoke(
                serve, ["--host", "0.0.0.0", "--port", "24272", "--reload"]
            )
            assert result.exit_code == 0
            assert not result.exception
            mock_uvicorn_run.assert_called_once_with(
                "bibra.main:app", host="0.0.0.0", port=24272, reload=True
            )

    def test_serve_with_short_port_option(self):
        """Test that serve passes the short -p port option to uvicorn.run."""
        with patch("bibra.cli.uvicorn.run") as mock_uvicorn_run:
            result = self.runner.invoke(serve, ["-p", "9999"])
            assert result.exit_code == 0
            assert not result.exception
            mock_uvicorn_run.assert_called_once_with(
                "bibra.main:app", host="127.0.0.1", port=9999, reload=False
            )


# Tests for the extract-url command.

MOCK_PDF_BYTES = b"%PDF-1.4 dummy content"


def _make_backend(json_payload=None):
    """Build a mock backend whose .extract() returns an object with a
    model_dump_json method, matching what asyncio.run(backend.extract(...))
    is expected to produce."""
    if json_payload is None:
        json_payload = {"title": "Some Paper", "authors": ["A. Author"]}

    mock_result = MagicMock()
    mock_result.model_dump_json.return_value = json.dumps(json_payload, indent=2)

    from bibra.backend.base import BaseBackend

    mock_backend = MagicMock()

    async def _extract(*args, **kwargs):
        return mock_result

    mock_backend.extract.side_effect = _extract
    # Bind the real helper so the temp-file write/cleanup runs (the CLI now
    # calls extract_from_bytes, not extract).
    mock_backend.extract_from_bytes = BaseBackend.extract_from_bytes.__get__(
        mock_backend, type(mock_backend)
    )
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
            patch("bibra.cli.fetch_file", new=AsyncMock(return_value=MOCK_PDF_BYTES)),
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

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
            patch("bibra.cli.fetch_file", new=AsyncMock(return_value=MOCK_PDF_BYTES)),
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

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
            patch("bibra.cli.fetch_file", new=AsyncMock(return_value=MOCK_PDF_BYTES)),
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

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
        """Test download failure is wrapped as 'Extraction failed (network):'."""
        import httpx2 as _httpx

        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch(
                "bibra.cli.fetch_file",
                new=AsyncMock(
                    side_effect=_httpx.HTTPError("Name or service not known")
                ),
            ),
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

            result = self.runner.invoke(
                extract_url, ["dummy", "https://bad.example.invalid/paper.pdf"]
            )

        assert result.exit_code != 0
        assert "Extraction failed (network):" in result.output

    def test_extract_url_generic_exception_converted_to_click_exception(self):
        """Test that a generic Exception during extraction is wrapped in
        ClickException with the 'Extraction failed:' prefix."""
        from bibra.backend.base import BaseBackend

        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.fetch_file", new=AsyncMock(return_value=MOCK_PDF_BYTES)),
            patch("bibra.backend.base.os.unlink"),
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_backend = MagicMock()

            async def _extract(*args, **kwargs):
                raise RuntimeError("PDF corrupted")

            mock_backend.extract.side_effect = _extract
            mock_backend.extract_from_bytes = BaseBackend.extract_from_bytes.__get__(
                mock_backend, type(mock_backend)
            )
            mock_registry.get_backend.return_value = mock_backend

            result = self.runner.invoke(
                extract_url, ["dummy", "https://example.com/paper.pdf"]
            )

        assert result.exit_code != 0
        assert "Extraction failed: PDF corrupted" in result.output

    def test_extract_url_uses_configured_proxy(self):
        """Test that the fetch policy passed to fetch_file carries the proxy."""
        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch(
                "bibra.cli.fetch_file", new=AsyncMock(return_value=MOCK_PDF_BYTES)
            ) as mock_fetch,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

            result = self.runner.invoke(
                extract_url,
                ["dummy", "https://example.com/paper.pdf"],
                env={"BIBRA_URL_PROXY": "http://proxy.example.com:8080"},
            )

        assert result.exit_code == 0
        args, _ = mock_fetch.call_args
        assert args[0] == "https://example.com/paper.pdf"
        assert args[1].proxy == "http://proxy.example.com:8080"

    def test_extract_url_pages_option_shown_in_help(self):
        """The --pages option should be documented in the help output."""
        result = self.runner.invoke(extract_url, ["--help"])
        assert result.exit_code == 0
        assert "--pages" in result.output

    def test_extract_url_with_pages_passes_parsed_pages(self):
        """--pages should be parsed and passed to extract_from_bytes."""
        captured = {}
        mock_result = MagicMock()
        mock_result.model_dump_json.return_value = "{}"

        from bibra.backend.base import BaseBackend

        mock_backend = MagicMock()

        async def _extract(*args, **kwargs):
            captured.update(kwargs)
            return mock_result

        mock_backend.extract.side_effect = _extract
        mock_backend.extract_from_bytes = BaseBackend.extract_from_bytes.__get__(
            mock_backend, type(mock_backend)
        )

        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch("bibra.cli.fetch_file", new=AsyncMock(return_value=MOCK_PDF_BYTES)),
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = mock_backend

            result = self.runner.invoke(
                extract_url,
                [
                    "dummy",
                    "https://example.com/paper.pdf",
                    "--pages",
                    "1,2,3,-1",
                ],
            )

        assert result.exit_code == 0
        assert captured["pages"] == [1, 2, 3, -1]

    def test_extract_url_with_invalid_pages(self):
        """An invalid --pages value should be a usage error."""
        with patch("bibra.cli.ProjectRegistry") as mock_registry_cls:
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

            result = self.runner.invoke(
                extract_url,
                ["dummy", "https://example.com/paper.pdf", "--pages", "bogus"],
            )

        assert result.exit_code != 0
        assert "Invalid page specification item" in result.output

    def test_extract_url_falls_back_to_direct_when_proxy_not_set(self, monkeypatch):
        """Unlike the API, the CLI is lenient: with BIBRA_URL_PROXY unset it
        behaves as if it were "direct" (full validation still applies)."""
        monkeypatch.delenv("BIBRA_URL_PROXY", raising=False)

        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch(
                "bibra.cli.fetch_file",
                new=AsyncMock(return_value=MOCK_PDF_BYTES),
            ) as mock_fetch,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

            result = self.runner.invoke(
                extract_url,
                ["dummy", "https://example.com/paper.pdf"],
            )

        assert result.exit_code == 0
        args, _ = mock_fetch.call_args
        assert args[0] == "https://example.com/paper.pdf"
        assert args[1].proxy == "direct"

    def test_extract_url_proxy_not_overridden_when_set(self, monkeypatch):
        """An explicitly configured proxy URL is used as-is by the CLI."""
        monkeypatch.setenv("BIBRA_URL_PROXY", "http://proxy.example.com:8080")

        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch(
                "bibra.cli.fetch_file",
                new=AsyncMock(return_value=MOCK_PDF_BYTES),
            ) as mock_fetch,
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

            result = self.runner.invoke(
                extract_url,
                ["dummy", "https://example.com/paper.pdf"],
            )

        assert result.exit_code == 0
        args, _ = mock_fetch.call_args
        assert args[1].proxy == "http://proxy.example.com:8080"

    def test_extract_url_policy_error_converted_to_click_exception(self):
        """A URL rejected by the fetch policy becomes a ClickException."""
        from bibra.net_security import UrlPolicyError

        with (
            patch("bibra.cli.ProjectRegistry") as mock_registry_cls,
            patch(
                "bibra.cli.fetch_file",
                new=AsyncMock(
                    side_effect=UrlPolicyError("URL rejected by fetch policy")
                ),
            ),
        ):
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry
            mock_registry.get_backend.return_value = _make_backend()

            result = self.runner.invoke(
                extract_url,
                ["dummy", "http://169.254.169.254/latest/meta-data/"],
            )

        assert result.exit_code != 0
        assert "Extraction failed (policy):" in result.output
        assert "URL rejected by fetch policy" in result.output
        assert "169.254.169.254" not in result.output


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


class TestCliStartupTime:
    """Startup time regression tests for the CLI to avoid accidentally making
    it slow to start.
    """

    MAX_HELP_WALL_TIME_S = 0.5
    RUNS = 3
    HELP_CMD: tuple[str, ...] = (
        sys.executable,
        "-c",
        "from bibra.cli import cli; cli()",
        "--help",
    )

    @classmethod
    def _run_help(cls) -> float:
        """Run `bibra --help` in a fresh subprocess and return the wall time."""
        start = time.perf_counter()
        subprocess.run(cls.HELP_CMD, check=True, capture_output=True)
        return time.perf_counter() - start

    def test_cli_help_starts_fast(self):
        """`bibra --help` must stay fast in a fresh interpreter.

        The minimum of several runs is used so that a single cold-cache or
        transiently slow measurement cannot fail the test, while a genuine
        regression (all runs slow) always does.
        """
        times = [self._run_help() for _ in range(self.RUNS)]
        elapsed = min(times)
        assert elapsed < self.MAX_HELP_WALL_TIME_S, (
            f"`bibra --help` took {elapsed:.2f} s (min of {times}); "
            f"exceeds the {self.MAX_HELP_WALL_TIME_S} s budget."
        )
