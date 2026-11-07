"""`astra plan [PATH] [--json]`: the planned results, their places and commands (§18, design
§4.12)."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import FAILED, environment, write_json, write_report


@click.command("plan")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Print the plan as JSON.")
def command(path: Path | None, as_json: bool) -> None:
    """Show the planned results of the analysis in PATH, each after what it reads.

    PATH is the analysis's folder, the current one by default. Each result is shown with its
    places, its record's and its bytes' (§18), and its command, run in its analysis's folder,
    with its placeholders filled in (§11), or the commit whose record it is read through (§17).
    Exits 1 where the analysis breaks a MUST, which is shown as `astra validate` shows it, and 2
    where it can't be read.
    """
    from astra import api

    with environment():
        try:
            found = api.plan(path)
        except api.InvalidAnalysisError as error:  # OPEN(O27)
            write_report(error.report, as_json)
            raise click.exceptions.Exit(FAILED) from None
    if as_json:
        write_json(found.to_json())
    else:
        from astra.cli.text.plan import show

        show(found)
