"""`astra info [PATH]`: the stack in brief (design §4.12)."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import read_stack


@click.command("info")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
def command(path: Path | None) -> None:
    """Show the stack of the analysis in PATH, in brief.

    PATH is the analysis's folder, the current one by default. Each analysis of its stack is
    shown with its declarations, inputs, outputs, decisions and universes, the root first. It
    checks nothing: `astra validate` does. Exits 1 where the analysis has no stack to show.
    """
    from astra.cli.text.info import show

    show(read_stack(path))  # OPEN(O22): text alone
