"""`astra validate [PATH] [--json] [--offline]`: the validator's report (design §4.12)."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import FAILED, environment, write_report


@click.command("validate")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Print the report as JSON.")
@click.option("--offline", is_flag=True, help="Fetch nothing: use only the commits fetched before.")
def command(path: Path | None, as_json: bool, offline: bool) -> None:
    """Validate the analysis in PATH.

    PATH is the analysis's folder, the current one by default. Analyses from another
    repository are fetched into the cache, once each; with --offline, nothing is fetched. Exits
    0 when the analysis is valid, 1 when it breaks a MUST, and 2 when it can't be validated.
    """
    from astra import api

    with environment():
        report = api.validate(path, offline=offline)
    write_report(report, as_json)
    if not report.valid:
        raise click.exceptions.Exit(FAILED)
