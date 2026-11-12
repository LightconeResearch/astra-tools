"""`astra view U [PATH] [--json]`: the stack as it is in one universe."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import FAILED, environment, write_json, write_report


@click.command("view")
@click.argument("universe")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Print the view as JSON.")
def command(universe: str, path: Path | None, as_json: bool) -> None:
    """Show the analysis in PATH as it is in UNIVERSE, one of its universes.

    PATH is the analysis's folder, the current one by default. Each analysis of its stack is
    shown, with whether it is built in UNIVERSE, the option selected for each decision, or that
    UNIVERSE doesn't use it (Results), each output's result there and its places, or why it has
    none, and the case each switch takes there (Elements). Exits 1 where the analysis
    breaks a MUST, which is shown as `astra validate` shows it, and 2 where it can't be read or
    has no universe UNIVERSE.
    """
    from astra import api

    with environment():
        try:
            found = api.view(universe, path)
        except api.InvalidAnalysisError as error:
            write_report(error.report, as_json)
            raise click.exceptions.Exit(FAILED) from None
        except api.RequestError as error:
            raise click.BadParameter(str(error), param_hint="UNIVERSE") from None
    if as_json:
        write_json(found.to_json())
    else:
        from astra.cli.text.view import show

        show(found)
