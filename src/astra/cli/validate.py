"""`astra validate [PATH] [--json] [--offline]`: the validator's report (design §4.12)."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import FAILED, fail, write_json


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
    from astra.cache import CacheError
    from astra.sources.git import GitError

    try:
        report = api.validate(path, offline=offline)
    except (api.NoAnalysisError, CacheError, GitError) as error:
        fail(str(error))
    except OSError as error:
        fail(f"can't read {error.filename}: {error.strerror}")
    if as_json:
        write_json(report.to_json())
    else:
        from astra.cli.text.validate import show

        show(report)
    if not report.valid:
        raise click.exceptions.Exit(FAILED)
