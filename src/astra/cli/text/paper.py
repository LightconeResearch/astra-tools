"""`astra paper verify`'s diagnostics as text, as `astra validate` shows its own."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import by_file, console
from astra.diagnostics import Diagnostic


def show(diagnostics: tuple[Diagnostic, ...]) -> None:
    out = console()
    by_file(out, diagnostics)
    # The codes of `evidence.quotes`, named here: this module imports neither it nor rapidfuzz.
    missing = sum(diagnostic.code == "EVIDENCE_PAPER_MISSING" for diagnostic in diagnostics)
    not_found = sum(diagnostic.code == "QUOTE_NOT_FOUND" for diagnostic in diagnostics)
    if missing or not_found:
        out.print(
            Text(
                f"{not_found} quote(s) not found in their paper; {missing} not sought, their "
                "paper not in the cache: `astra paper add` it.",
                style="red",
            )
        )
    else:
        out.print(Text("Each quote cited by DOI is in its paper.", style="green"))
