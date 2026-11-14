"""`astra init [DIRECTORY] [--check] [--json]`: converge a folder into a minimal
analysis, idempotently."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click

from astra.cli import FAILED, fail

GITIGNORE = """\
# ASTRA Analysis
__pycache__/
*.py[cod]
.venv/
.ipynb_checkpoints/
.DS_Store
"""
"""The `.gitignore` a new analysis gets."""


@click.command("init")
@click.argument("directory", default=".", type=click.Path(file_okay=False, path_type=Path))
@click.option(
    "--check",
    "check_only",
    is_flag=True,
    help="Report what would be created without writing anything; exit 1 if the scaffold is "
    "not converged.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit the convergence report as JSON.")
def command(directory: Path, check_only: bool, as_json: bool) -> None:
    """Converge DIRECTORY into a minimal ASTRA analysis scaffold (idempotent).

    Safe to re-run at any time: creates whatever is missing (astra.yaml, .gitignore, a git
    repository) and never overwrites existing files. A folder that already holds an
    astra.yaml, or any other files, is adopted, not rejected. Where a git repository already
    holds DIRECTORY, no new one is made inside it. The astra.yaml is empty: a spec_version and
    a label; universes, when there are some, are written in it.

    DIRECTORY is the folder to converge (default: the current folder).

    \b
    Examples:
        astra init my-analysis
        astra init --check --json   # is this folder scaffolded? (for scripts and agents)
    """
    from astra.scaffold import create_boilerplate, write_text
    from astra.sources.git import GitError, Repository

    write = not check_only
    report: dict[str, list[str]] = {"created": [], "repaired": [], "unchanged": [], "warnings": []}
    try:
        if (directory / "astra.yaml").exists():
            report["unchanged"].append("astra.yaml")
        else:
            report["created"].append("astra.yaml")
            if write:
                create_boilerplate(directory)
        if (directory / ".gitignore").exists():
            report["unchanged"].append(".gitignore")
        else:
            report["created"].append(".gitignore")
            if write:
                write_text(directory / ".gitignore", GITIGNORE)
        existing = directory.resolve()
        while not existing.is_dir():  # a folder not made yet: the nearest one above
            existing = existing.parent
        held = Repository.discover(existing) is not None
        if held:
            report["unchanged"].append(".git")
        else:
            report["created"].append(".git")
            if write:
                Repository.init(directory)
                _first_commit(directory)
    except GitError as error:
        fail(str(error))
    except OSError as error:
        fail(f"can't write {error.filename}: {error.strerror}")
    converged = not report["created"]
    if as_json:
        click.echo(json.dumps({"converged": converged, **report}, indent=2))
    elif check_only:
        if converged:
            click.echo(f"✓ {directory} is converged — nothing to do")
        for item in report["created"]:
            click.echo(f"  would create {item}")
    elif converged:
        click.echo(f"✓ {directory} already converged")
    else:
        for item in report["created"]:
            click.echo(f"✓ created {item}")
        click.echo(f"✓ Converged ASTRA analysis scaffold: {directory}")
    if check_only and not converged:
        raise click.exceptions.Exit(FAILED)


def _first_commit(directory: Path) -> None:
    """Commit what the new repository holds, as the user, where git can: a repository made
    without one is a repository all the same."""
    for args in (("add", "."), ("commit", "--quiet", "-m", "Initial ASTRA analysis structure")):
        if subprocess.run(["git", *args], cwd=directory, capture_output=True).returncode:
            return
