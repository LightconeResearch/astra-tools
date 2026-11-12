"""The universe view as text: each analysis of the stack, whether it is built in the universe,
each decision's selected option, or that the universe doesn't use it, each switch's case taken
there, and each output's places there, with the commit they are read at for an analysis from a
commit, or why it has none."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import console, file_named
from astra.diagnostics import Location
from astra.view import DecisionView, OutputView, UniverseView


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
            out.print(Text(f"  {id_:<12} {_decision(decision)}"))
        written = member.analysis.outputs if member.analysis is not None else {}
        for id_, output in analysis.outputs.items():
            switch = id_ in written and written[id_].is_switch
            out.print(Text(f"  {id_:<12} {_switch(output) if switch else _output(output)}"))


def _decision(decision: DecisionView) -> str:
    """The option selected, marked where the universe doesn't use the decision; or else that it
    doesn't, or that none is selected."""
    unused = decision.used is False
    if decision.selected is not None:
        return decision.selected + ("  (unused)" if unused else "")
    return "unused" if unused else "no option selected"


def _switch(output: OutputView) -> str:
    """The case a switch takes, or that it takes nothing, or that what it takes is undetermined."""
    if output.takes is not None:
        return f"takes {output.takes}"
    return "takes nothing" if output.built is False else "undetermined"


def _output(output: OutputView) -> str:
    """An output's places, or that it isn't built, or that it has no planned result."""
    owner = output.result and output.result.owner.commit
    at = f" at {owner}" if owner else ""
    places = [f"{place.address}  {place.bytes}{at}" for place in output.places]
    if places:
        return ", ".join(places)
    return "not built" if output.built is False else "no planned result"
