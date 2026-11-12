"""Universes as text: an analysis's universes and imports, and one universe's effective
selection."""

from __future__ import annotations

from rich.text import Text

from astra import model
from astra.cli.text import console
from astra.universes import Selection


def show_universes(analysis: model.Analysis) -> None:
    out = console()
    if not analysis.universes:
        out.print("The analysis has no universes.")
    for id_, universe in analysis.universes.items():
        line = Text(id_, style="bold")
        if universe.is_import:
            line.append(f"  imports {universe.analysis}.{universe.universe}")
        elif universe.derived_from is not None:
            line.append(f"  derived from {universe.derived_from}")
        if universe.label is not None:
            line.append(f"  {universe.label}")
        out.print(line)


def show_selection(selection: Selection, derived_from: str | None) -> None:
    out = console()
    heading = Text(selection.universe.id, style="bold")
    if derived_from is not None:
        heading.append(f"  derived from {derived_from}")
    out.print(heading)
    if not selection.entries:
        out.print("  selects nothing")
    for entry in selection.entries:
        line = Text(f"  {entry.key}: {entry.option}")
        if not selection.own(entry):
            assert entry.owner is not None  # the universe whose own `decisions` set it
            line.append(f"  (from {entry.owner.id})", style="dim")
        out.print(line)
