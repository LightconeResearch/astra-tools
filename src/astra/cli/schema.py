"""`astra schema export|show`: astra-spec's LinkML schemas, as it ships them."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import click

SCHEMAS = MappingProxyType(
    {
        "analysis": "analysis.yaml",
        "insights": "insight.yaml",
        "provenance": "provenance.yaml",
        "types": "types.yaml",
    }
)
"""Each schema `show` prints, with its file. Universes are part of `analysis` since ASTRA 0.1."""


@click.group("schema")
def command() -> None:
    """Schema commands."""


@command.command("export")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default="schemas",
    help="Output directory (default: schemas/)",
)
def schema_export(output: Path) -> None:
    """Export LinkML schemas to files."""
    from astra.scaffold import write_text

    exported = []
    for schema_file in sorted(_directory().glob("*.yaml")):
        write_text(output / schema_file.name, schema_file.read_text(encoding="utf-8"))
        exported.append(schema_file.name)
    click.echo(f"✓ Exported schemas to {output}/")
    for name in exported:
        click.echo(f"  • {output}/{name}")


@command.command("show")
@click.argument("schema_type", type=click.Choice(sorted(SCHEMAS)))
def schema_show(schema_type: str) -> None:
    """Print a LinkML schema to stdout."""
    click.echo((_directory() / SCHEMAS[schema_type]).read_text(encoding="utf-8"), nl=False)


def _directory() -> Path:
    """The folder of astra-spec's LinkML schemas: the one that holds analysis.yaml."""
    from importlib.resources import files

    return Path(str(files("astra.schema") / "analysis.yaml")).parent
