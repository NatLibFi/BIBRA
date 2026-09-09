"""CLI interface for BIBRA."""

import asyncio
import dataclasses
import os
import tempfile

import click
import uvicorn
from dotenv import load_dotenv

from bibra.config import (
    URL_FETCH_DIRECT,
    ConfigError,
    ProjectNotFoundError,
    ProjectRegistry,
    load_url_fetch_policy,
)
from bibra.net_security import UrlPolicyError, fetch_file_sync


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
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    default=None,
    help="Write JSON output to file instead of stdout",
)
def extract(project_id: str, file_path: str, config: str | None, output: str | None):
    """Extract publication metadata from a PDF or image file."""
    registry = ProjectRegistry(config)

    try:
        backend = registry.get_backend(project_id)
    except ProjectNotFoundError as e:
        raise click.UsageError(str(e)) from None
    except ConfigError as e:
        raise click.ClickException(str(e)) from None

    try:
        result = asyncio.run(backend.extract([file_path]))
    except Exception as e:
        raise click.ClickException(f"Extraction failed: {e}") from e

    json_output = result.model_dump_json(indent=2)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(json_output + "\n")
        click.echo(f"Output written to {output}")
    else:
        click.echo(json_output)


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
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    default=None,
    help="Write JSON output to file instead of stdout",
)
def extract_url(project_id: str, url: str, config: str | None, output: str | None):
    """Extract publication metadata from a PDF file at a URL."""

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
    registry = ProjectRegistry(config)

    try:
        backend = registry.get_backend(project_id)
    except ProjectNotFoundError as e:
        raise click.UsageError(str(e)) from None
    except ConfigError as e:
        raise click.ClickException(str(e)) from None

    policy = load_url_fetch_policy()
    if policy.proxy is None:
        policy = dataclasses.replace(policy, proxy=URL_FETCH_DIRECT)

    try:
        data = fetch_file_sync(url, policy)
    except UrlPolicyError as e:
        raise click.ClickException(f"Extraction failed: {e}") from None
    except Exception as e:
        raise click.ClickException(f"Extraction failed: {e}") from e

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(data)

        result = asyncio.run(backend.extract([tmp_path]))
    except Exception as e:
        raise click.ClickException(f"Extraction failed: {e}") from e
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError as e:
                click.echo(
                    f"Warning: could not remove temporary file {tmp_path}: {e}",
                    err=True,
                )

    json_output = result.model_dump_json(indent=2)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(json_output + "\n")
        click.echo(f"Output written to {output}")
    else:
        click.echo(json_output)
