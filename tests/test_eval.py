"""Tests for the eval command and evaluation pipeline."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from bibra.cli import cli
from bibra.downloader import Downloader
from bibra.evaluator import load_ground_truth, run_evaluation


class TestDownloader:
    """Tests for the Downloader class."""

    def test_download_creates_file_in_temp_dir(self, tmp_path):
        """Test that download saves the file to the temp directory."""
        downloader = Downloader(str(tmp_path))

        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.iter_content.return_value = [b"%PDF-1.4 dummy content"]
        mock_response.raise_for_status = MagicMock()

        with patch("bibra.downloader.requests.get", return_value=mock_response):
            filepath = downloader.download("https://example.com/doc.pdf")

        assert filepath.startswith(str(tmp_path))
        assert filepath.endswith(".pdf")
        with open(filepath, "rb") as f:
            assert f.read() == b"%PDF-1.4 dummy content"

    def test_download_falls_back_to_bin_extension(self, tmp_path):
        """Test that download uses .bin when Content-Type is unknown."""
        downloader = Downloader(str(tmp_path))

        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "application/octet-stream"}
        mock_response.iter_content.return_value = [b"raw bytes"]
        mock_response.raise_for_status = MagicMock()

        with patch("bibra.downloader.requests.get", return_value=mock_response):
            filepath = downloader.download("https://example.com/file")

        assert filepath.endswith(".bin")

    def test_download_no_content_type_header(self, tmp_path):
        """Test that download handles missing Content-Type header."""
        downloader = Downloader(str(tmp_path))

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.iter_content.return_value = [b"data"]
        mock_response.raise_for_status = MagicMock()

        with patch("bibra.downloader.requests.get", return_value=mock_response):
            filepath = downloader.download("https://example.com/file")

        assert filepath.endswith(".bin")

    def test_download_image_extension(self, tmp_path):
        """Test that download correctly handles image Content-Types."""
        downloader = Downloader(str(tmp_path))

        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.iter_content.return_value = [b"\x89PNG"]
        mock_response.raise_for_status = MagicMock()

        with patch("bibra.downloader.requests.get", return_value=mock_response):
            filepath = downloader.download("https://example.com/image")

        assert filepath.endswith(".png")

    def test_downloader_context_manager(self):
        """Test that Downloader works as a context manager."""
        with Downloader() as downloader:
            assert isinstance(downloader, Downloader)
            assert downloader.temp_dir is not None


class TestLoadGroundTruth:
    """Tests for loading ground truth records."""

    def test_load_single_file(self, tmp_path):
        """Test loading records from a single JSONL file."""
        record = {
            "url": "https://example.com/doc.pdf",
            "ground_truth": {"title": "Test Title", "year": "2024"},
        }
        jsonl_file = tmp_path / "ground_truth.jsonl"
        jsonl_file.write_text(json.dumps(record) + "\n")

        records = load_ground_truth([str(jsonl_file)])
        assert len(records) == 1
        assert records[0]["url"] == "https://example.com/doc.pdf"

    def test_load_multiple_files(self, tmp_path):
        """Test loading records from multiple JSONL files."""
        file1 = tmp_path / "gt1.jsonl"
        file1.write_text(
            json.dumps({"url": "https://a.pdf", "ground_truth": {}})
            + "\n"
            + json.dumps({"url": "https://b.pdf", "ground_truth": {}})
            + "\n"
        )
        file2 = tmp_path / "gt2.jsonl"
        file2.write_text(
            json.dumps({"url": "https://c.pdf", "ground_truth": {}}) + "\n"
        )

        records = load_ground_truth([str(file1), str(file2)])
        assert len(records) == 3

    def test_load_skips_empty_lines(self, tmp_path):
        """Test that empty lines in JSONL are skipped."""
        jsonl_file = tmp_path / "ground_truth.jsonl"
        jsonl_file.write_text(json.dumps({"url": "https://a.pdf"}) + "\n\n" + "\n")

        records = load_ground_truth([str(jsonl_file)])
        assert len(records) == 1


class TestRunEvaluation:
    """Tests for the evaluation pipeline."""

    def test_run_evaluation_returns_results(self):
        """Test that run_evaluation returns one result per record."""

        async def mock_extract(file_paths):
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {"title": "Extracted Title"}
            return mock_result

        mock_backend = MagicMock()
        mock_backend.extract = mock_extract

        records = [
            {
                "url": "https://example.com/doc.pdf",
                "ground_truth": {"title": "Ground Truth Title"},
            }
        ]

        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.iter_content.return_value = [b"dummy"]
        mock_response.raise_for_status = MagicMock()

        with patch("bibra.downloader.requests.get", return_value=mock_response):
            results = run_evaluation(mock_backend, records)

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/doc.pdf"
        assert results[0]["ground_truth"] == {"title": "Ground Truth Title"}
        assert results[0]["match"] is None

    def test_run_evaluation_skips_records_without_url(self):
        """Test that records missing 'url' are skipped."""
        mock_backend = MagicMock()

        records = [
            {"ground_truth": {"title": "No URL"}},  # should be skipped
        ]

        results = run_evaluation(mock_backend, records)
        assert len(results) == 0
        mock_backend.extract.assert_not_called()


class TestEvalCommand:
    """Tests for the eval CLI command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_eval_help(self):
        """Test eval help output."""
        result = self.runner.invoke(cli, ["eval", "--help"])
        assert result.exit_code == 0
        assert "Evaluate metadata extraction" in result.output
        assert "PROJECT_ID" in result.output
        assert "GROUND_TRUTH_FILES" in result.output

    def test_eval_no_files(self):
        """Test eval command with no ground truth files."""
        result = self.runner.invoke(cli, ["eval", "dummy"])
        assert result.exit_code != 0

    def test_eval_nonexistent_project(self, tmp_path):
        """Test eval command with a nonexistent project ID."""
        jsonl_file = tmp_path / "gt.jsonl"
        jsonl_file.write_text(json.dumps({"url": "https://example.com/doc.pdf"}) + "\n")
        result = self.runner.invoke(cli, ["eval", "nonexistent", str(jsonl_file)])
        assert result.exit_code != 0
        assert "Unknown project" in result.output

    def test_eval_empty_ground_truth(self, tmp_path):
        """Test eval command with empty JSONL file."""
        jsonl_file = tmp_path / "gt.jsonl"
        jsonl_file.write_text("")
        result = self.runner.invoke(cli, ["eval", "dummy", str(jsonl_file)])
        assert result.exit_code != 0
        assert "No ground truth records found" in result.output
