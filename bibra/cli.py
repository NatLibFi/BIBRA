import click

from bibra.api.v0.routes import PROJECTS
from bibra.backend.dummy import DummyBackend


def _make_list_template(column_headings: tuple, *rows: tuple) -> str:
    """Create a format string for a aligned table."""
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


@cli.command("list-projects")
def list_projects():
    """List available projects."""
    column_headings = ("Project ID", "Project Name", "Description", "Created At")
    table = [
        (
            proj["id"],
            proj["name"],
            proj["description"],
            proj["created_at"],
        )
        for proj in PROJECTS
    ]
    template = _make_list_template(column_headings, *table)
    header = template.format(*column_headings)
    click.echo(header)
    click.echo("-" * len(header))
    for row in table:
        click.echo(template.format(*row))


@cli.command("extract")
@click.argument("project_id")
@click.argument("files", type=click.Path(exists=True), nargs=-1, required=True)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Write JSON output to file instead of stdout",
)
def extract(project_id: str, files: tuple[str, ...], output: str | None):
    """Extract publication metadata from PDF or image files."""
    # TODO - In a real implementation, select the backend based on project_id
    backend = DummyBackend()
    result = backend.extract(list(files))
    json_output = result.model_dump_json(indent=2)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(json_output + "\n")
        click.echo(f"Output written to {output}")
    else:
        click.echo(json_output)
