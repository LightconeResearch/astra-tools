"""`astra check [PATH] [--at REV] [--json]`: each planned result's record and bytes statuses,
and the evidence's."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import FAILED, environment, write_json


@click.command("check")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option(
    "--at",
    "at",
    metavar="REV",
    help="Check the analysis as it is at the commit REV names, with its records and bytes there.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the report as JSON.")
def command(path: Path | None, at: str | None, as_json: bool) -> None:
    """Check the records and bytes of the planned results of the analysis in PATH.

    PATH is the analysis's folder, the current one by default. Each planned result is shown at
    each of its places with its record's status, unchanged, stale or missing, and its bytes',
    present or absent, and why; then each evidence with the status of what it cites.
    Where the analysis breaks a MUST, its errors come first, as `astra validate` shows them,
    and only the results they leave determined are shown. Exits 0 when the analysis is valid
    and every planned result and evidence is unchanged, 1 when one isn't or the analysis breaks
    a MUST, and 2 where it can't be read or REV names no commit.
    """
    from astra import api

    with environment():
        try:
            report = api.check(path, at=at)
        except api.RequestError as error:
            raise click.BadParameter(str(error), param_hint="--at") from None
    if as_json:
        write_json(report.to_json())
    else:
        from astra.cli.text.check import show

        show(report)
    if not report.ok:
        raise click.exceptions.Exit(FAILED)
