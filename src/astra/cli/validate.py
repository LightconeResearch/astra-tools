"""`astra validate [FILE] [-e|--verify-evidence] [--skip-evidence] [--json] [--offline]`: the
validator's report, for one analysis or every root analysis under the current folder."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import click

from astra.cli import FAILED, environment, json_string

if TYPE_CHECKING:
    from astra.stack import Stack

SKIPPED = frozenset({"node_modules", "venv", "__pycache__", "results"})
"""Folders the search for analyses doesn't enter, beside hidden ones: vendored code, and the
results an analysis makes."""


@click.command("validate")
@click.argument("file", required=False, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-e",
    "--verify-evidence",
    is_flag=True,
    help="Also seek each quote the evidence takes from a paper, as `astra paper verify` does "
    "(the papers must be in the cache: `astra paper add`).",
)
@click.option(
    "--skip-evidence",
    is_flag=True,
    help="Say nothing of the evidence: neither seek its quotes nor suggest --verify-evidence.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the report as a single JSON-encoded string (exit code unchanged).",
)
@click.option("--offline", is_flag=True, help="Fetch nothing: use only the commits fetched before.")
def command(
    file: Path | None, verify_evidence: bool, skip_evidence: bool, as_json: bool, offline: bool
) -> None:
    """Validate an analysis, or every analysis under the current folder.

    FILE is an analysis's astra.yaml, or its folder; each analysis it declares is validated
    with it. With no FILE, every root analysis under the current folder is validated: each
    astra.yaml no other one declares, hidden, vendored and results folders skipped. Analyses
    from another repository are fetched into the cache, once each; with --offline, nothing is
    fetched.

    --verify-evidence also seeks each quote that the evidence takes from a paper cited by DOI,
    in its paper in the cache, as `astra paper verify` does: a quote not found, or whose paper
    isn't in the cache, is an error.

    With --json, the whole report is emitted as one JSON-encoded string on stdout, safe to
    embed verbatim in any JSON document, while the exit code still carries pass or fail. Exits
    0 when every analysis is valid, 1 when one breaks a MUST, and 2 when one can't be
    validated.
    """
    with json_string(as_json):
        if file is None:
            _validate_all(Path.cwd(), verify_evidence, skip_evidence, offline)
        elif not _validate_one(_folder(file), verify_evidence, skip_evidence, offline):
            raise click.exceptions.Exit(FAILED)


def _folder(file: Path) -> Path:
    """The folder of the analysis FILE names: FILE itself, or the folder of its astra.yaml."""
    if file.is_dir():
        return file
    if file.name == "astra.yaml":
        return file.parent
    raise click.BadParameter(
        f"{file} is neither an astra.yaml nor a folder: universes are in astra.yaml since "
        "ASTRA 0.1, so there is no universe file to validate",
        param_hint="FILE",
    )


def _validate_all(top: Path, verify_evidence: bool, skip_evidence: bool, offline: bool) -> None:
    """Validate each root analysis under `top`; exit 1 where one breaks a MUST."""
    from astra import api

    found = _analyses(top)
    if not found:
        click.echo("Error: no astra.yaml found here.")
        raise click.exceptions.Exit(FAILED)
    declared: set[Path] = set()
    failed: list[str] = []
    roots = 0
    for folder in found:  # a folder before those below it
        if folder in declared:
            continue
        with environment():
            bound = api.bind(folder)
        if bound.stack is not None:
            declared |= _declared(bound.stack, folder)
        if roots:
            click.echo()
        roots += 1
        if not _validate_one(folder, verify_evidence, skip_evidence, offline):
            failed.append(_named(folder, top))
    click.echo()
    if failed:
        click.echo(f"{len(failed)}/{roots} analysis(es) failed validation: {', '.join(failed)}")
        raise click.exceptions.Exit(FAILED)
    click.echo(f"All {roots} analysis(es) passed validation.")


def _validate_one(folder: Path, verify_evidence: bool, skip_evidence: bool, offline: bool) -> bool:
    """Validate the analysis in `folder` and print its report; whether it is valid and, with
    `verify_evidence`, its every quote found."""
    from astra import api
    from astra.cli.text.validate import show

    with environment():
        report = api.validate(folder, offline=offline)
    show(report)
    if not report.valid or skip_evidence:
        return report.valid
    if not verify_evidence:
        _suggest(folder)
        return True
    from astra.cli.paper import show_quotes

    return show_quotes(folder)


def _suggest(folder: Path) -> None:
    """Where the analysis's evidence takes quotes from papers, say how to seek them."""
    from astra import api

    with environment():
        stack = api.bind(folder).stack
    if stack is None:
        return
    analysis = stack.analysis(stack.root)
    insights = (*analysis.prior_insights.values(), *analysis.findings.values())
    quoted = sum(
        item.doi is not None and item.quote is not None
        for insight in insights
        for item in insight.evidence
    )
    if quoted:
        click.echo(
            f"Note: the evidence takes {quoted} quote(s) from papers: run with "
            "--verify-evidence to seek them."
        )


def _analyses(top: Path) -> list[Path]:
    """Every folder under `top` with an astra.yaml, each before those below it."""
    found: list[Path] = []
    for folder, children, files in os.walk(top):
        children[:] = sorted(c for c in children if not c.startswith(".") and c not in SKIPPED)
        if "astra.yaml" in files:
            found.append(Path(folder).resolve())
    return found


def _declared(stack: Stack, folder: Path) -> set[Path]:
    """The folders, in the working tree, of the analyses `stack`'s root declares, directly or
    not: they are validated with it."""
    top = folder.resolve()
    for _ in Path(stack.root.folder).parts:  # the root's folder is a path from the tree's top
        top = top.parent
    return {
        (top / identity.folder).resolve()
        for identity in stack.analyses
        if identity.commit is None and identity != stack.root
    }


def _named(folder: Path, top: Path) -> str:
    """A folder's astra.yaml, from `top`."""
    return str((folder / "astra.yaml").relative_to(top.resolve()))
