"""`astra paper verify`'s warnings as text, as `astra validate` shows its diagnostics."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import by_file, console
from astra.diagnostics import Diagnostic


def show(warnings: tuple[Diagnostic, ...]) -> None:
    out = console()
    by_file(out, warnings)
    if warnings:
        out.print(f"{len(warnings)} warning(s), advisory only: no verdict changes.")
    else:
        out.print(Text("No warnings: each quote cited by DOI is in its paper.", style="green"))
