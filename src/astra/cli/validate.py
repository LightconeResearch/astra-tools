"""`astra validate [FILE] [-e|--verify-evidence] [--skip-evidence] [--json] [--offline]`: the
validator's report, for one analysis or every root analysis under the current folder."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from astra.cli import FAILED, environment, write_json

if TYPE_CHECKING:
    from astra import model
    from astra.stack import Stack

SKIPPED = frozenset({"node_modules", "venv", "__pycache__", "results"})
"""Folders the search for analyses doesn't enter, beside hidden ones: vendored code, and the
results an analysis makes."""

SHAPE = "astra-validation-reports/1"
"""The JSON of `validate --json` with no FILE: every root analysis's report."""


@click.command("validate")
@click.argument("file", required=False, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-e",
    "--verify-evidence",
    is_flag=True,
    help="Verify evidence quotes (in prior_insights and findings) exist in source papers "
    "(requires papers to be cached)",
)
@click.option(
    "--skip-evidence",
    is_flag=True,
    help="Skip evidence verification even if prior insights or findings are present",
)
@click.option("--json", "as_json", is_flag=True, help="Print the report as JSON.")
@click.option("--offline", is_flag=True, help="Fetch nothing: use only the commits fetched before.")
def command(
    file: Path | None, verify_evidence: bool, skip_evidence: bool, as_json: bool, offline: bool
) -> None:
    """Validate an ASTRA analysis, or the whole project.

    FILE is an analysis's astra.yaml, or its folder; each analysis it declares is validated
    with it. With no FILE, every root analysis under the current directory is validated: each
    astra.yaml no other one declares; hidden, vendored and results directories are skipped.
    Analyses from another repository are fetched into the cache, once each; with --offline,
    nothing is fetched.

    Evidence verification (--verify-evidence) checks that quotes in prior_insights and
    findings actually exist in the source papers. Papers must be cached first using 'astra
    paper add'. Artifact-backed evidence is reported as SKIPPED.

    With --json, the report is printed as JSON: `astra-validation-report/1` for FILE, and
    `astra-validation-reports/1`, which holds each root analysis's report, with no FILE. With
    --verify-evidence, a report has an `evidence` member too. The exit code is unchanged: 0
    when every analysis is valid, 1 when one breaks a MUST or a quote isn't verified, and 2
    when one can't be validated.
    """
    options = (verify_evidence and not skip_evidence, skip_evidence, as_json, offline)
    if file is not None:
        valid, document = _validate_one(_folder(file), *options)
        if as_json:
            write_json(document)
        if not valid:
            raise click.exceptions.Exit(FAILED)
        return
    top = Path.cwd()
    roots = _roots(top)
    if not roots:
        click.echo("Error: No astra.yaml found here.", err=as_json)
        raise click.exceptions.Exit(FAILED)
    failed: list[str] = []
    documents: list[dict[str, Any]] = []
    for index, folder in enumerate(roots):
        if index and not as_json:
            click.echo()
        valid, document = _validate_one(folder, *options)
        documents.append(document)
        if not valid:
            failed.append(str((folder / "astra.yaml").relative_to(top.resolve())))
    if as_json:
        write_json({"shape": SHAPE, "valid": not failed, "reports": documents})
    elif failed:
        click.echo()
        click.echo(f"{len(failed)}/{len(roots)} file(s) failed validation: {', '.join(failed)}")
    else:
        click.echo()
        click.echo(f"All {len(roots)} file(s) passed validation.")
    if failed:
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


def _validate_one(
    folder: Path, verify_evidence: bool, skip_evidence: bool, as_json: bool, offline: bool
) -> tuple[bool, dict[str, Any]]:
    """Validate the analysis in `folder`, and print its report unless `as_json`. Gives whether
    it is valid and, with `verify_evidence`, its every quote verified; and the report as JSON."""
    from astra import api

    with environment():
        report = api.validate(folder, offline=offline)
    document = report.to_json()
    if not as_json:
        from astra.cli.text.validate import show

        show(report)
    if not report.valid or skip_evidence:
        return report.valid, document
    insights = _insights(folder)
    if not verify_evidence:
        if not as_json:
            _suggest(insights)
        return True, document
    results, verified = _verify(insights, as_json)
    document["evidence"] = results
    return verified, document


def _insights(folder: Path) -> dict[str, dict[str, model.Insight]]:
    """The prior insights and findings of the analysis in `folder`, valid."""
    from astra import api

    with environment():
        stack = api.bind(folder).stack
    if stack is None:
        return {}
    analysis = stack.analysis(stack.root)
    found = {"prior_insights": analysis.prior_insights, "findings": analysis.findings}
    return {label: dict(insights) for label, insights in found.items() if insights}


def _suggest(insights: dict[str, dict[str, model.Insight]]) -> None:
    """Where the analysis has evidence, say how to verify its quotes."""
    counts = {
        label: (len(found), sum(len(insight.evidence) for insight in found.values()))
        for label, found in insights.items()
    }
    prior, prior_evidence = counts.get("prior_insights", (0, 0))
    findings, finding_evidence = counts.get("findings", (0, 0))
    if prior_evidence + finding_evidence:
        click.echo(
            f"\nNote: {prior} prior insight(s) ({prior_evidence} evidence) and "
            f"{findings} finding(s) ({finding_evidence} evidence) found."
        )
        click.echo("Run with --verify-evidence to verify quotes exist in papers.")


def _evidence(insights: dict[str, model.Insight]) -> dict[str, dict[str, Any]]:
    """Insights as the verification reads them: each evidence with an id, its place in the
    insight, and its location's page, `page=N`, as the page to seek the quote on first."""
    shaped: dict[str, dict[str, Any]] = {}
    for insight_id, insight in insights.items():
        items = []
        for index, item in enumerate(insight.evidence):
            page = None
            if item.location is not None and item.location.value.startswith("page="):
                number = item.location.value.removeprefix("page=")
                page = int(number) if number.isdigit() else None
            quote = item.quote
            items.append(
                {
                    "id": f"evidence[{index}]",
                    "doi": item.doi or "",
                    "version": item.version,
                    "artifact": item.artifact,
                    "quote": None
                    if quote is None
                    else {"exact": quote.exact, "prefix": quote.prefix, "suffix": quote.suffix},
                    "location": None if page is None else {"page": page},
                }
            )
        shaped[insight_id] = {"id": insight_id, "evidence": items}
    return shaped


def _verify(
    insights: dict[str, dict[str, model.Insight]], as_json: bool
) -> tuple[list[dict[str, Any]], bool]:
    """Verify the quotes of `insights` against the cached papers, and print the outcome unless
    `as_json`. Gives each evidence's result, and whether none failed."""
    from astra.papers.cache import PaperCache
    from astra.verification.cache import VerificationCache
    from astra.verification.core import VerificationStatus, verify_all_insights

    passed = (VerificationStatus.VERIFIED, VerificationStatus.CACHED)
    results: list[dict[str, Any]] = []
    failed = 0
    if insights and not as_json:
        click.echo("\nVerifying evidence...")
    for label, found in insights.items():
        verified = cached = skipped = artifacts = failures = 0
        outcome = verify_all_insights(_evidence(found), PaperCache(), VerificationCache())
        for insight_id, result in outcome.items():
            for item in result.evidence_results:
                results.append(
                    {
                        "in": label,
                        "insight": insight_id,
                        "evidence": item.evidence_id,
                        "doi": item.doi or None,
                        "version": item.version,
                        "status": item.status.value,
                        "pages": list(item.quote_found_pages),
                        "message": item.message,
                    }
                )
                if item.status in passed:
                    verified += 1
                    cached += item.status == VerificationStatus.CACHED
                elif item.status == VerificationStatus.SKIPPED:
                    skipped += 1
                    artifacts += "Artifact quote verification" in item.message
                else:
                    failures += 1
                    if not as_json:
                        mark = "!" if item.status == VerificationStatus.ERROR else "✗"
                        click.echo(f"  {mark} [{insight_id}] {item.evidence_id}: {item.message}")
        failed += failures
        if as_json:
            continue
        parts = [f"{verified}/{verified + skipped + failures} verified"]
        if cached:
            parts.append(f"{cached} from cache")
        if artifacts:
            parts.append(f"{artifacts} SKIPPED (artifact)")
        if skipped - artifacts:
            parts.append(f"{skipped - artifacts} skipped")
        click.echo(f"✓ Evidence ({label}): " + ", ".join(parts))
    if failed and not as_json:
        click.echo(f"\nError: {failed} evidence item(s) failed verification")
        click.echo("\nTo fix:")
        click.echo("  1. Check that quotes are exact copies from the paper")
        click.echo("  2. Verify the DOI and version are correct")
        click.echo("  3. Ensure the paper is cached: astra paper add <doi>")
    return results, not failed


def _roots(top: Path) -> list[Path]:
    """The folder of each root analysis under `top`: each astra.yaml that no other one found
    declares, directly or not, a folder before those below it."""
    from astra import api

    found: list[Path] = []
    for folder, children, files in os.walk(top):
        children[:] = sorted(c for c in children if not c.startswith(".") and c not in SKIPPED)
        if "astra.yaml" in files:
            found.append(Path(folder).resolve())
    declared: set[Path] = set()
    roots: list[Path] = []
    for root in found:
        if root in declared:
            continue
        roots.append(root)
        with environment():
            stack = api.bind(root).stack
        if stack is not None:
            declared |= _declared(stack, root)
    return roots


def _declared(stack: Stack, folder: Path) -> set[Path]:
    """The folders, in the working tree, of the analyses `stack`'s root declares, directly or
    not: they are validated with it."""
    top = folder
    for _ in Path(stack.root.folder).parts:  # the root's folder is a path from the tree's top
        top = top.parent
    return {
        (top / identity.folder).resolve()
        for identity in stack.analyses
        if identity.commit is None and identity != stack.root
    }
