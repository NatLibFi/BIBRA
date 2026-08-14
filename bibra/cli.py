"""CLI interface for BIBRA."""

import asyncio
import json

import click
from dotenv import load_dotenv

from bibra.config import (
    ConfigError,
    ProjectNotFoundError,
    ProjectRegistry,
)
from bibra.evaluator import load_ground_truth, run_evaluation


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


@cli.command("eval")
@click.argument("project_id")
@click.argument(
    "ground_truth_files",
    type=click.Path(exists=True, dir_okay=False),
    nargs=-1,
    required=True,
)
@click.option(
    "--config",
    "-c",
    default=None,
    help="Path to the project configuration file (overrides BIBRA_CONFIG).",
)
def eval_(
    project_id: str,
    ground_truth_files: tuple[str, ...],
    config: str | None,
):
    """Evaluate metadata extraction against ground truth JSONL files."""
    registry = ProjectRegistry(config)

    try:
        backend = registry.get_backend(project_id)
    except ProjectNotFoundError as e:
        raise click.UsageError(str(e)) from None
    except ConfigError as e:
        raise click.ClickException(str(e)) from None

    records = load_ground_truth(list(ground_truth_files))

    if not records:
        raise click.ClickException("No ground truth records found in input files")

    try:
        results = run_evaluation(backend, records)
    except Exception as e:
        raise click.ClickException(f"Evaluation failed: {e}") from e

    click.echo(json.dumps(results, indent=2))
