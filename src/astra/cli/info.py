"""`astra info [-f FILE] [-d] [-i] [-o] [--json]`: the stack in brief."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import FAILED, find_analysis, json_string, read_stack


@click.command("info")
@click.option(
    "-f",
    "--file",
    type=click.Path(exists=True, path_type=Path),
    help="Analysis file (default: astra.yaml in the current or a parent folder).",
)
@click.option("-d", "--decisions", is_flag=True, help="Show the decisions.")
@click.option("-i", "--inputs", is_flag=True, help="Show the inputs.")
@click.option("-o", "--outputs", is_flag=True, help="Show the outputs.")
@click.option(
    "--json", "as_json", is_flag=True, help="Emit the output as a single JSON-encoded string."
)
def command(file: Path | None, decisions: bool, inputs: bool, outputs: bool, as_json: bool) -> None:
    """Show information about an analysis.

    Each analysis of its stack is shown, the root first, with its declarations, inputs,
    outputs, decisions and universes; with -d, -i or -o, only those asked for. It checks
    nothing: `astra validate` does. With --json, the output is emitted as one JSON-encoded
    string on stdout, safe to embed verbatim in any JSON document. Exits 1 where there is no
    analysis, or no stack to show.
    """
    with json_string(as_json):
        found = find_analysis() if file is None else file
        if found is None:
            click.echo("Error: No astra.yaml found.")
            raise click.exceptions.Exit(FAILED)
        folder = found if found.is_dir() else found.parent
        asked = {
            name
            for name, wanted in (("decisions", decisions), ("inputs", inputs), ("outputs", outputs))
            if wanted
        }
        from astra.cli.text.info import show

        show(read_stack(folder), asked or None)
