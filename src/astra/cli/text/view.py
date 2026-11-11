"""The universe view as text: each analysis of the stack, whether it is built in the universe,
each decision's selected option, and each output's places there, with the commit they are read
at for an analysis from a commit (§17)."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import console, file_named
from astra.diagnostics import Location
from astra.view import UniverseView


def show(view: UniverseView) -> None:
    out = console()
    out.print(Text(f"universe {view.universe}", style="bold"))
    for analysis in view.analyses:
        member = analysis.member
        file = file_named(
            Location(member.file, "", None, None, None, member.identity.commit, member.url)
        )
        built = "built" if analysis.built else f"not built in {view.universe}"
        out.print(Text.assemble((file, "bold"), f"  {built}"))
        for id_, decision in analysis.decisions.items():
            shown = decision.selected or "no option selected"
            out.print(Text(f"  {id_:<12} {shown}"))
        for id_, output in analysis.outputs.items():
            owner = output.result and output.result.owner.commit
            at = f" at {owner}" if owner else ""
            places = [f"{place.address}  {place.bytes}{at}" for place in output.places]
            shown = ", ".join(places) or "no planned result"
            out.print(Text(f"  {id_:<12} {shown}"))
