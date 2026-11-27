"""CLI interface for BIBRA."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import click
import httpx2
import uvicorn
from dotenv import load_dotenv

from bibra.backend import BaseBackend
from bibra.config import ConfigError, ProjectNotFoundError, ProjectRegistry
from bibra.net_security import UrlPolicyError, fetch_file, load_url_fetch_policy
from bibra.pages import MAX_PAGES, parse_page_spec
from bibra.types import PublicationMetadata

if TYPE_CHECKING:
    from bibraeval.aggregator import AggregationMode

PAGES_HELP = (
    "Pages to extract, 1-based and comma-separated; negative counts "
    "from the last page; ranges allowed (e.g. 1-4,-2--1); at most "
    f"{MAX_PAGES} pages. Page 0 is not allowed. Overrides the "
    "project-configured pages."
)


def _pages_option(
    pages: str | None,
) -> list[int] | None:
    """Parse the --pages option, raising a usage error on bad input."""
    if pages is None:
        return None
    try:
        return parse_page_spec(pages)
    except ValueError as e:
        raise click.UsageError(str(e)) from e


def _make_list_template(column_headings: tuple, *rows: tuple) -> str:
    """Create a format string for an aligned table."""
    if not rows:
        col_widths = [len(h) for h in column_headings]
    else:
        col_widths = [
            max(
                len(column_headings[i]),
                max((len(str(row[i])) for row in rows), default=0),
            )
            for i in range(len(column_headings))
        ]

    return "  ".join(f"{{:<{w}}}" for w in col_widths)


@click.group()
@click.version_option()
def cli():
    """BIBRA - Bibliographic metadata extraction tool."""
    load_dotenv()


@cli.command("eval")
@click.option(
    "--ground-truth",
    "gt_path",
    required=True,
    type=click.Path(exists=True, readable=True),
    help="Ground truth JSONL file or directory of JSON metadata records.",
)
@click.option(
    "--predictions",
    "pred_path",
    required=True,
    type=click.Path(exists=True, readable=True),
    help="Prediction JSONL file or directory of JSON metadata records.",
)
@click.option(
    "--field-metric-config",
    "--field_metric_config",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    default=None,
    help="YAML config for metrics and weights; default: exact matching, weight 1.",
)
@click.option(
    "--mode",
    type=click.Choice(["doc-avg", "field-avg", "micro-avg"]),
    default="field-avg",
    show_default=True,
    help="Aggregation mode for summary metrics.",
)
@click.option(
    "--drop-mismatched-doc-ids",
    is_flag=True,
    help="Evaluate only shared document IDs; by default mismatches are errors.",
)
@click.option(
    "--results-dir",
    type=click.Path(file_okay=False, writable=True),
    default=None,
    help="Export summary YAML and comparison/intermediate CSVs to this directory.",
)
def evaluate(
    gt_path: str,
    pred_path: str,
    field_metric_config: str | None,
    mode: AggregationMode,
    drop_mismatched_doc_ids: bool,
    results_dir: str | None,
) -> None:
    """Evaluate BIBRA predictions against ground truth and print a summary table."""
    # Keep scipy/polars imports off the startup path for other CLI commands.
    from bibraeval.evaluator import Evaluator
    from polars.exceptions import PolarsError
    from yaml import YAMLError

    try:
        evaluator = Evaluator(
            gt_path=gt_path,
            pred_path=pred_path,
            schema=PublicationMetadata,
            mode=mode,
            field_metric_config=field_metric_config,
            drop_mismatched_doc_ids=drop_mismatched_doc_ids,
        )
        summary = evaluator.compute_metrics(results_dir=results_dir)
    except (OSError, ValueError, TypeError, YAMLError, PolarsError) as e:
        raise click.ClickException(f"Evaluation failed: {e}") from e
    click.echo(summary)


@cli.command("list-projects")
@click.option(
    "--config",
    "-c",
    default=None,
    help="Path to the project configuration file (overrides BIBRA_CONFIG).",
)
def list_projects(config: str | None):
    """List configured projects."""
    registry = ProjectRegistry(config)
    try:
        registry.load()
        projects = registry.list_projects()
    except ConfigError as e:
        raise click.ClickException(str(e)) from None

    column_headings = ("Project ID", "Project Name", "Description")
    table = [(proj["id"], proj["name"], proj["description"]) for proj in projects]
    template = _make_list_template(column_headings, *table)
    header = template.format(*column_headings)
    click.echo(header)
    click.echo("-" * len(header))
    for row in table:
        click.echo(template.format(*row))


def _get_backend(project_id: str, config: str | None) -> BaseBackend:
    """Look up a configured backend, raising Click errors on failure."""
    registry = ProjectRegistry(config)
    try:
        return registry.get_backend(project_id)
    except ProjectNotFoundError as e:
        raise click.UsageError(str(e)) from None
    except ConfigError as e:
        raise click.ClickException(str(e)) from None


def _emit_json(result: PublicationMetadata, output: str | None) -> None:
    """Write the result as JSON to a file or stdout."""
    json_output = result.model_dump_json(indent=2)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(json_output + "\n")
        click.echo(f"Output written to {output}")
    else:
        click.echo(json_output)


@cli.command("extract")
@click.argument("project_id")
@click.argument(
    "file_path", type=click.Path(exists=True, dir_okay=False), nargs=1, required=True
)
@click.option(
    "--config",
    "-c",
    default=None,
    help="Path to the project configuration file (overrides BIBRA_CONFIG).",
)
@click.option("--pages", default=None, help=PAGES_HELP)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    default=None,
    help="Write JSON output to file instead of stdout",
)
def extract(
    project_id: str,
    file_path: str,
    config: str | None,
    pages: str | None,
    output: str | None,
):
    """Extract publication metadata from a PDF or image file."""
    backend = _get_backend(project_id, config)
    selected_pages = _pages_option(pages)

    try:
        result = asyncio.run(backend.extract([file_path], pages=selected_pages))
    except Exception as e:
        raise click.ClickException(f"Extraction failed: {e}") from e

    _emit_json(result, output)


@cli.command("serve")
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Interface address to bind the server to.",
)
@click.option(
    "--port",
    "-p",
    default=8000,
    show_default=True,
    type=int,
    help="Port to bind the server to.",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reloading (useful during development).",
)
def serve(host: str, port: int, reload: bool):
    """Serve the BIBRA API server (FastAPI + Web UI) in the foreground."""
    # The app is passed as a string import path so that uvicorn's
    # auto-reloader can import it in a separate worker process.
    uvicorn.run("bibra.main:app", host=host, port=port, reload=reload)


@cli.command("extract-url")
@click.argument("project_id")
@click.argument("url")
@click.option(
    "--config",
    "-c",
    default=None,
    help="Path to the project configuration file (overrides BIBRA_CONFIG).",
)
@click.option("--pages", default=None, help=PAGES_HELP)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    default=None,
    help="Write JSON output to file instead of stdout",
)
def extract_url(
    project_id: str,
    url: str,
    config: str | None,
    pages: str | None,
    output: str | None,
):
    """Extract publication metadata from a PDF file at a URL.

    The download is performed with the SSRF-hardened fetch layer
    (``bibra.net_security``): the URL and every redirect hop are validated
    against the fetch policy, and the downloaded bytes are verified before
    being handed to the backend.

    Unlike the REST API, the CLI is more lenient about egress: when
    BIBRA_URL_PROXY is not set it behaves as if it were set to "direct",
    i.e. it fetches directly (with full in-app validation) instead of
    refusing. Set BIBRA_URL_PROXY to a proxy URL to route CLI downloads
    through a proxy.
    """
    backend = _get_backend(project_id, config)
    selected_pages = _pages_option(pages)

    policy = load_url_fetch_policy(cli_fallback=True)

    async def _run() -> PublicationMetadata:
        data = await fetch_file(url, policy)
        return await backend.extract_from_bytes(data, pages=selected_pages)

    try:
        result = asyncio.run(_run())
    except UrlPolicyError as e:
        # Policy rejection (blocked destination, bad scheme, size cap, ...).
        raise click.ClickException(f"Extraction failed (policy): {e}") from None
    except httpx2.HTTPError as e:
        # Network/download failure (DNS, connection, timeout, HTTP status).
        raise click.ClickException(f"Extraction failed (network): {e}") from e
    except Exception as e:
        raise click.ClickException(f"Extraction failed: {e}") from e

    _emit_json(result, output)
