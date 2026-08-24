"""Tests for the eval command and evaluation pipeline."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from bibra.cli import cli
from bibra.downloader import Downloader
from bibra.evaluator import (
    _compare_e_issn,
    _compare_fuzzy_string,
    _compare_set,
    _compare_simple_string,
    aggregate_results,
    load_ground_truth,
    run_evaluation,
)

# ---------------------------------------------------------------------------
# Downloader tests (unchanged)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# load_ground_truth tests (unchanged)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Comparison helper tests
# ---------------------------------------------------------------------------


class TestCompareSimpleString:
    """Tests for _compare_simple_string helper."""

    def test_both_none(self):
        match, score = _compare_simple_string(None, None)
        assert match == "not-relevant"
        assert score == 1

    def test_true_none(self):
        match, score = _compare_simple_string(None, "predicted")
        assert match == "found-nonexistent"
        assert score == 0

    def test_pred_none(self):
        match, score = _compare_simple_string("truth", None)
        assert match == "not-found"
        assert score == 0

    def test_exact_match(self):
        match, score = _compare_simple_string("value", "value")
        assert match == "exact"
        assert score == 1

    def test_mismatch(self):
        match, score = _compare_simple_string("truth", "wrong")
        assert match == "wrong"
        assert score == 0


class TestCompareFuzzyString:
    """Tests for _compare_fuzzy_string helper."""

    def test_exact(self):
        match, score = _compare_fuzzy_string("Title", "Title")
        assert match == "exact"
        assert score == 1

    def test_case_insensitive(self):
        match, score = _compare_fuzzy_string("Title", "title")
        assert match == "case"
        assert score == 1

    def test_almost_match(self):
        """Very similar strings should be 'almost'."""
        true_str = "A Very Long Title Here"
        pred_str = "A Very Long Tile Here"
        match, score = _compare_fuzzy_string(true_str, pred_str)
        assert match in ("almost", "almost-case", "exact")
        assert score == 1

    def test_wrong(self):
        match, score = _compare_fuzzy_string("Completely Different", "Unrelated Text")
        assert match == "wrong"
        assert score == 0

    def test_pred_none(self):
        match, score = _compare_fuzzy_string("truth", None)
        assert match == "not-found"
        assert score == 0

    def test_both_none(self):
        match, score = _compare_fuzzy_string(None, None)
        assert match == "not-relevant"
        assert score == 1


class TestCompareSet:
    """Tests for _compare_set helper."""

    def test_both_empty(self):
        match, score = _compare_set([], [])
        assert match == "not-relevant"
        assert score == 1

    def test_true_empty(self):
        match, score = _compare_set([], ["pred"])
        assert match == "found-nonexistent"
        assert score == 0

    def test_pred_empty(self):
        match, score = _compare_set(["true"], [])
        assert match == "not-found"
        assert score == 0

    def test_exact(self):
        match, score = _compare_set(["a", "b"], ["b", "a"])
        assert match == "exact"
        assert score == 1

    def test_subset(self):
        match, score = _compare_set(["a", "b", "c"], ["a", "b"])
        assert match == "subset"
        assert 0 < score < 1

    def test_superset(self):
        match, score = _compare_set(["a"], ["a", "b", "c"])
        assert match == "superset"
        assert 0 < score < 1

    def test_overlap(self):
        match, score = _compare_set(["a", "b"], ["b", "c"])
        assert match == "overlap"
        assert 0 < score < 1

    def test_no_overlap(self):
        match, score = _compare_set(["a", "b"], ["c", "d"])
        assert match == "wrong"
        assert score == 0


class TestCompareEISSN:
    """Tests for _compare_e_issn helper."""

    def test_exact_match(self):
        match, score = _compare_e_issn("1234-5678", "1234-5678", "8765-4321")
        assert match == "exact"
        assert score == 1

    def test_wrong(self):
        match, score = _compare_e_issn("1234-5678", "0000-0000", "8765-4321")
        assert match == "wrong"
        assert score == 0

    def test_printed_issn_found_with_true_val(self):
        """Prediction matches p_issn but ground truth has e_issn."""
        match, score = _compare_e_issn("1234-5678", "8765-4321", "8765-4321")
        assert match == "printed-issn"
        assert score == 0

    def test_printed_issn_found_no_true_val(self):
        """Prediction matches p_issn and there is no e_issn in ground truth."""
        match, score = _compare_e_issn(None, "8765-4321", "8765-4321")
        # Base result is "found-nonexistent", returned early.
        assert match == "found-nonexistent"
        assert score == 0

    def test_pred_none(self):
        match, score = _compare_e_issn("1234-5678", None, "8765-4321")
        assert match == "not-found"
        assert score == 0


# ---------------------------------------------------------------------------
# run_evaluation tests
# ---------------------------------------------------------------------------


class TestRunEvaluation:
    """Tests for the evaluation pipeline."""

    def test_run_evaluation_returns_per_field_results(self):
        """Test that run_evaluation returns one result per field per record."""
        from bibra.types import PublicationMetadata

        async def mock_extract(file_paths):
            return PublicationMetadata(
                title="Extracted Title",
                language="en",
            )

        mock_backend = MagicMock()
        mock_backend.extract = mock_extract

        records = [
            {
                "url": "https://example.com/doc.pdf",
                "ground_truth": {"title": "Extracted Title", "language": "en"},
            }
        ]

        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.iter_content.return_value = [b"dummy"]
        mock_response.raise_for_status = MagicMock()

        with patch("bibra.downloader.requests.get", return_value=mock_response):
            results = run_evaluation(mock_backend, records)

        # Should have one result per field (12 fields from PublicationMetadata).
        assert len(results) == 12
        # Check a title field result.
        title_result = next(r for r in results if r["field"] == "title")
        assert title_result["match_type"] == "exact"
        assert title_result["score"] == 1

    def test_run_evaluation_skips_records_without_url(self):
        """Test that records missing 'url' are skipped."""
        mock_backend = MagicMock()

        records = [
            {"ground_truth": {"title": "No URL"}},  # should be skipped
        ]

        results = run_evaluation(mock_backend, records)
        assert len(results) == 0
        mock_backend.extract.assert_not_called()

    def test_run_evaluation_handles_hyphenated_keys(self):
        """Test that ground truth with hyphenated keys (e-isbn) is parsed."""
        from bibra.types import PublicationMetadata

        async def mock_extract(file_paths):
            return PublicationMetadata(
                e_isbn=["978-3-16-148410-0"],
            )

        mock_backend = MagicMock()
        mock_backend.extract = mock_extract

        records = [
            {
                "url": "https://example.com/doc.pdf",
                "ground_truth": {
                    "e-isbn": ["978-3-16-148410-0"],
                },
            }
        ]

        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.iter_content.return_value = [b"dummy"]
        mock_response.raise_for_status = MagicMock()

        with patch("bibra.downloader.requests.get", return_value=mock_response):
            results = run_evaluation(mock_backend, records)

        e_isbn_result = next(r for r in results if r["field"] == "e_isbn")
        assert e_isbn_result["match_type"] == "exact"
        assert e_isbn_result["score"] == 1


# ---------------------------------------------------------------------------
# aggregate_results tests
# ---------------------------------------------------------------------------


class TestAggregateResults:
    """Tests for the aggregate_results function."""

    def test_aggregate_produces_tsv_header(self):
        results = [
            {
                "url": "https://a.pdf",
                "language": "en",
                "field": "title",
                "predicted_val": "Title",
                "true_val": "Title",
                "match_type": "exact",
                "score": 1,
            }
        ]
        tsv = aggregate_results(results)
        assert tsv.startswith("language\tfield\tmean_score\tcount")

    def test_aggregate_mean_and_count(self):
        results = [
            {
                "url": "https://a.pdf",
                "language": "en",
                "field": "title",
                "predicted_val": "A",
                "true_val": "A",
                "match_type": "exact",
                "score": 1,
            },
            {
                "url": "https://b.pdf",
                "language": "en",
                "field": "title",
                "predicted_val": "B",
                "true_val": "C",
                "match_type": "wrong",
                "score": 0,
            },
        ]
        tsv = aggregate_results(results)
        lines = tsv.split("\n")
        # Header + one data line + overall summary.
        assert len(lines) == 3
        assert lines[1] == "en\ttitle\t0.5000\t2"
        assert lines[2] == "-\t-\t0.5000\t2"

    def test_aggregate_groups_by_language_and_field(self):
        results = [
            {
                "url": "https://a.pdf",
                "language": "en",
                "field": "title",
                "predicted_val": "A",
                "true_val": "A",
                "match_type": "exact",
                "score": 1,
            },
            {
                "url": "https://b.pdf",
                "language": "de",
                "field": "title",
                "predicted_val": "B",
                "true_val": "B",
                "match_type": "exact",
                "score": 1,
            },
            {
                "url": "https://a.pdf",
                "language": "en",
                "field": "year",
                "predicted_val": "2024",
                "true_val": "2024",
                "match_type": "exact",
                "score": 1,
            },
        ]
        tsv = aggregate_results(results)
        lines = tsv.split("\n")
        assert len(lines) == 5  # header + 3 groups + overall summary

    def test_aggregate_filters_fields(self):
        results = [
            {
                "url": "https://a.pdf",
                "language": "en",
                "field": "title",
                "predicted_val": "A",
                "true_val": "A",
                "match_type": "exact",
                "score": 1,
            },
            {
                "url": "https://a.pdf",
                "language": "en",
                "field": "year",
                "predicted_val": "2024",
                "true_val": "2024",
                "match_type": "exact",
                "score": 1,
            },
        ]
        tsv = aggregate_results(results, fields=("title",))
        lines = tsv.split("\n")
        assert len(lines) == 3  # header + title only + overall summary
        assert "title" in lines[1]
        assert "year" not in tsv

    def test_aggregate_empty_results(self):
        tsv = aggregate_results([])
        lines = tsv.split("\n")
        assert len(lines) == 2  # header + overall summary (0.0000)
        assert lines[0] == "language\tfield\tmean_score\tcount"
        assert lines[1] == "-\t-\t0.0000\t0"

    def test_aggregate_null_language(self):
        results = [
            {
                "url": "https://a.pdf",
                "language": None,
                "field": "title",
                "predicted_val": "A",
                "true_val": "A",
                "match_type": "exact",
                "score": 1,
            }
        ]
        tsv = aggregate_results(results)
        lines = tsv.split("\n")
        assert lines[1] == "\ttitle\t1.0000\t1"


# ---------------------------------------------------------------------------
# CLI eval command tests
# ---------------------------------------------------------------------------


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

    def test_eval_outputs_tsv(self, tmp_path):
        """Test that eval command outputs TSV format."""
        jsonl_file = tmp_path / "gt.jsonl"
        jsonl_file.write_text(
            json.dumps(
                {
                    "url": "https://example.com/doc.pdf",
                    "ground_truth": {"title": "Test", "language": "en"},
                }
            )
            + "\n"
        )

        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.iter_content.return_value = [b"dummy"]
        mock_response.raise_for_status = MagicMock()

        with patch("bibra.downloader.requests.get", return_value=mock_response):
            result = self.runner.invoke(cli, ["eval", "dummy", str(jsonl_file)])

        assert result.exit_code == 0
        assert "language\tfield\tmean_score\tcount" in result.output
