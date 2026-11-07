"""The validation report as text: grouped by file, a file read at a commit named with it and
the remote it came from, as `line:col level CODE message`."""

from __future__ import annotations

from itertools import groupby
from types import MappingProxyType

from rich.text import Text

from astra.cli.text import console, file_named
from astra.validate import ValidationReport

_STYLES = MappingProxyType({"error": "bold red", "warning": "yellow"})


def show(report: ValidationReport) -> None:
    out = console()
    for file, diagnostics in groupby(report.diagnostics, key=lambda d: file_named(d.location)):
        out.print(Text(file, style="bold"))
        for diagnostic in diagnostics:
            line = Text("  ")
            if diagnostic.location.line is not None:
                line.append(f"{diagnostic.location.line}:{diagnostic.location.column} ")
            line.append(diagnostic.level, style=_STYLES[diagnostic.level])
            line.append(f" {diagnostic.code}", style="bold")
            line.append(f" {diagnostic.message}")
            out.print(line)
    errors = sum(d.level == "error" for d in report.diagnostics)
    warnings = len(report.diagnostics) - errors
    verdict = Text("valid" if report.valid else "invalid", style="green" if report.valid else "red")
    out.print(
        Text.assemble(f"{report.root}: ", verdict, f", {errors} error(s), {warnings} warning(s)")
    )
    if report.unchecked:
        out.print(
            f"{len(report.unchecked)} validator rules aren't checked by this astra-tools yet."
        )
