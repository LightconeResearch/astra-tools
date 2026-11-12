"""view(): the stack as it is in one universe of the root, for UIs.

Each analysis of the stack, the root first, with its fields as its `astra.yaml` writes them and
whether it is built in the universe; each of its decisions, the option the universe selects for
it and whether the universe uses it, with the root driving (Results *uses*); and each of its
outputs, whether it is built there (Results *built*), the case it takes there for a switch
(Elements *takes*), and its planned result there, with its places: its result in the universe,
or its one result where it is built once. Like the plan, the view is made only of a valid stack
(`api.view`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

from astra.diagnostics import Catalogue
from astra.plan import root_universe
from astra.rules.context import Context
from astra.stack import Element, Kind, Member, Stack
from astra.universes import Place, Planned, places

SHAPE = "astra-universe-view/1"


@dataclass(frozen=True)
class DecisionView:
    used: bool | None  # whether the universe uses it, with the root driving (Results *uses*);
    # None where that turns on a switch that is undetermined
    selected: str | None  # the option the universe selects; None where it selects none


@dataclass(frozen=True)
class OutputView:
    built: bool | None  # whether it is built in the universe (Results *built*), as an output built
    # once always is; None where that is undetermined
    takes: str | None  # for a switch, the case it takes there, as written; None where it takes
    # none, and for an output other than a switch (Elements *takes*)
    result: Planned | None  # its planned result in the universe, or once; None where none is, as
    # for a switch, which has no result
    places: tuple[Place, ...]  # the result's, one for each of its names


@dataclass(frozen=True)
class AnalysisView:
    member: Member  # its identity, its file, and its fields, as `analysis` and `document`
    built: bool  # whether it is built in the universe: the root, or driven there
    decisions: Mapping[str, DecisionView]
    outputs: Mapping[str, OutputView]


@dataclass(frozen=True)
class UniverseView:
    """The stack as it is in one of the root's universes."""

    root: str  # the root's astra.yaml, as a Location's `file` names it
    universe: str  # the universe's id
    analyses: tuple[AnalysisView, ...]

    def to_json(self) -> dict[str, Any]:
        """The view as `astra-universe-view/1`."""
        # The exact JSON form.
        return {
            "shape": SHAPE,
            "root": self.root,
            "universe": self.universe,
            "analyses": [_analysis(analysis) for analysis in self.analyses],
        }


def _analysis(analysis: AnalysisView) -> dict[str, Any]:
    member = analysis.member
    assert member.document is not None  # every file of a valid stack is a valid document
    return {
        **asdict(member.identity),
        "file": member.file,
        "built": analysis.built,
        "fields": member.document.value,
        "decisions": {id_: asdict(decision) for id_, decision in analysis.decisions.items()},
        "outputs": {
            id_: {"built": output.built, "takes": output.takes, "result": _result(output)}
            for id_, output in analysis.outputs.items()
        },
    }


def _result(output: OutputView) -> dict[str, Any] | None:
    result = output.result
    if result is None:
        return None
    return {
        "names": list(result.names),
        "owner": asdict(result.owner),
        "universe": None if result.universe is None else result.universe.id,
        "places": [asdict(place) for place in output.places],
    }


def view(stack: Stack, universe: str) -> UniverseView:
    """`stack`, a valid stack, as it is in the root's universe `universe`. Raises RequestError
    where the root has no such universe."""
    context = Context(stack, Catalogue.load())
    element = root_universe(stack, universe)
    selection = context.selections[element]
    assert selection is not None  # every universe of a valid stack has one
    built = context.building.universes[element]
    run = context.building.run  # the root's
    used = run.used.get(element, frozenset())
    maybe = run.maybe.get(element, frozenset())
    meaning = context.meaning
    analyses: list[AnalysisView] = []
    for member, analysis in stack.determined():
        decisions: dict[str, DecisionView] = {}
        for id_ in analysis.decisions:
            decision = Element(member.identity, "decision", id_)
            selected = min(selection.options(decision), default=None)
            uses = True if decision in used else None if decision in maybe else False
            decisions[id_] = DecisionView(uses, selected)
        outputs: dict[str, OutputView] = {}
        for id_, written in analysis.outputs.items():
            kind: Kind = "switch" if written.is_switch else "output"
            output = Element(member.identity, kind, id_)
            at = element if kind == "switch" or output in context.per_universe else None
            takes = None
            if kind == "switch":
                taken = meaning.taken(output, element)
                takes = None if taken is None or taken.case is None else taken.case.written
            result = context.building.planned.get((output, at))
            found = () if result is None else places(stack, result)
            outputs[id_] = OutputView(meaning.built(output, at), takes, result, found)
        analyses.append(
            AnalysisView(
                member,
                member.identity in built,
                MappingProxyType(decisions),
                MappingProxyType(outputs),
            )
        )
    return UniverseView(stack.analyses[stack.root].file, universe, tuple(analyses))
