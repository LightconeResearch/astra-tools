"""`astra schema show|export`: astra-spec's JSON Schemas, byte for byte (Annex D)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import click

from astra.cli import fail
from astra.contract import SCHEMA_NAMES, SchemaName, schema_file


@click.group("schema")
def command() -> None:
    """Show or export the JSON Schemas of ASTRA files.

    They are astra-spec's: `analysis` for astra.yaml, `provenance` for a record, and
    `provenance.open` for a record of a later minor version.
    """


@command.command("show")
@click.argument("name", type=click.Choice(SCHEMA_NAMES))
def show(name: SchemaName) -> None:
    """Print the JSON Schema NAME."""
    click.echo(schema_file(name).read_bytes(), nl=False)


@command.command("export")
@click.argument("folder", type=click.Path(file_okay=False, path_type=Path))
def export(folder: Path) -> None:
    """Write the three JSON Schemas into FOLDER, as NAME.schema.json."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name in SCHEMA_NAMES:
            path = folder / f"{name}.schema.json"
            descriptor, temporary = tempfile.mkstemp(dir=folder, prefix=f".{path.name}.")
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(schema_file(name).read_bytes())
            os.chmod(temporary, 0o644)
            os.replace(temporary, path)
            click.echo(path)
    except OSError as error:
        fail(f"can't write to {folder}: {error.strerror}")
