"""`astra plan [PATH] [--json] [--notes]`: the planned results, their places and commands, and
the plan's notes (§18, design §4.6, §4.12)."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import FAILED, environment, write_json, write_report


@click.command("plan")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Print the plan as JSON.")
@click.option("--notes", "listed", is_flag=True, help="List each note, not only their counts.")
def command(path: Path | None, as_json: bool, listed: bool) -> None:
    """Show the planned results of the analysis in PATH, each after what it reads.

    PATH is the analysis's folder, the current one by default. Each result is shown with its
    places, its record's and its bytes' (§18), the container and resources its recipe asks for,
    and its command, run in its analysis's folder, with its placeholders filled in (§11), or the
    commit whose record it is read through (§17). Then come the notes, none of them a breach,
    counted by kind, and listed with --notes (the JSON lists every one): pins that name another
    analysis's universe only because their file has no universe of that id (§16), results with
    two names (§18), outputs with no planned result (§18), outputs that aren't built in some
    universe because a switch they read has no case there for the option selected (Elements),
    results that are one computation in several universes, and commands that name a path outside
    their analysis's folder, or in a folder below it that holds an analysis of its own
    (CODE_OUTSIDE_ANALYSIS, §21). Pins, outputs and commands are counted and listed where they
    concern what the analysis in PATH builds: a pin a planned result reads through, an output or
    a command of the analysis or of one its universes drive; a line gives the whole stack's count
    where it is more. Exits 1 where the analysis breaks a MUST, which is shown as `astra
    validate` shows it, and 2 where it can't be read.
    """
    from astra import api

    with environment():
        try:
            found = api.plan(path)
        except api.InvalidAnalysisError as error:
            write_report(error.report, as_json)
            raise click.exceptions.Exit(FAILED) from None
    if as_json:
        write_json(found.to_json())
    else:
        from astra.cli.text.plan import show

        show(found, listed=listed)
