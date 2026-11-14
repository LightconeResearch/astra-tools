"""The validation report as text: grouped by file, a file read at a commit named with it and
the remote it came from, as `line:col level CODE message`."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import by_file, console
from astra.validate import ValidationReport


def show(report: ValidationReport) -> None:
    out = console()
    by_file(out, report.diagnostics)
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
