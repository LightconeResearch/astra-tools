"""`astra paper verify`'s diagnostics as text, as `astra validate` shows its own."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import by_file, console
from astra.diagnostics import Diagnostic


def show(diagnostics: tuple[Diagnostic, ...]) -> None:
    out = console()
    by_file(out, diagnostics)
    errors = sum(diagnostic.level == "error" for diagnostic in diagnostics)
    warnings = len(diagnostics) - errors
    unsought = f"{warnings} not sought, their paper not in the cache"
    if errors:
        out.print(Text(f"{errors} quote(s) not found in their paper; {unsought}.", style="red"))
    elif warnings:
        out.print(f"Each quote sought is in its paper; {unsought}.")
    else:
        out.print(Text("Each quote cited by DOI is in its paper.", style="green"))
