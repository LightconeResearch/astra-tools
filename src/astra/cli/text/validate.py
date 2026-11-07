"""The validation report as text: grouped by file, a file read at a commit named with it and
the remote it came from, as `line:col level CODE message`."""

from __future__ import annotations

from itertools import groupby

from rich.text import Text

from astra.cli.text import console, file_named, rule_line
from astra.validate import ValidationReport


def show(report: ValidationReport) -> None:
    out = console()
    for file, diagnostics in groupby(report.diagnostics, key=lambda d: file_named(d.location)):
        out.print(Text(file, style="bold"))
        for d in diagnostics:
            out.print(rule_line(d.location, d.level, d.code, d.message))
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
