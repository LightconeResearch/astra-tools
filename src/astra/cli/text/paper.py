"""`astra paper verify`'s warnings as text, as `astra validate` shows its diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.table import Table
from rich.text import Text

from astra.cli.text import by_file, console
from astra.diagnostics import Diagnostic

if TYPE_CHECKING:
    from astra.evidence.papers import Record


def show(warnings: tuple[Diagnostic, ...]) -> None:
    out = console()
    by_file(out, warnings)
    if warnings:
        out.print(f"{len(warnings)} warning(s), advisory only: no verdict changes.")
    else:
        out.print(Text("No warnings: each quote cited by DOI is in its paper.", style="green"))


def show_papers(papers: tuple[Record, ...]) -> None:
    """`astra paper list`: the cached papers, as a table."""
    out = console()
    if not papers:
        out.print(Text("No papers cached", style="dim"))
        return
    table = Table(show_header=True, expand=True)
    table.add_column("DOI", no_wrap=True)
    table.add_column("Ver", no_wrap=True)
    table.add_column("Title", ratio=2)
    table.add_column("Retrieved", no_wrap=True)
    for paper in papers:
        version = "-" if paper.version is None else str(paper.version)
        title = Text(paper.title) if paper.title else Text("(unknown)", style="dim")
        table.add_row(paper.doi, version, title, paper.retrieved_at[:10])
    out.print(table)
    out.print(Text(f"\n{len(papers)} paper(s) cached", style="dim"))
