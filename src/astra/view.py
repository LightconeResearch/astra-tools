"""view(): the stack as it is in one universe of the root, for UIs (§12, §16, §18; design §4.6).

Each analysis of the stack, the root first, with its fields as its `astra.yaml` writes them and
whether it is built in the universe (§16 *The universe being built*); each of its decisions and
the option the universe selects for it (§12); and each of its outputs and its planned result
there, with its places (§18): its result in the universe, or its one result where it is built
once. Like the plan, the view is made only of a valid stack (`api.view`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

from astra.diagnostics import Catalogue
from astra.plan import root_universe
from astra.rules.context import Context
from astra.stack import Element, Member, Stack
from astra.universes import Place, Planned, places

SHAPE = "astra-universe-view/1"


@dataclass(frozen=True)
class DecisionView:
    selected: str | None  # the option the universe selects; None where it selects none


@dataclass(frozen=True)
class OutputView:
    result: Planned | None  # its planned result in the universe, or once; None where none is
    places: tuple[Place, ...]  # the result's, one for each of its names


@dataclass(frozen=True)
class AnalysisView:
    member: Member  # its identity, its file, and its fields, as `analysis` and `document`
    built: bool  # whether it is built in the universe: the root, or driven there (§16)
    decisions: Mapping[str, DecisionView]
    outputs: Mapping[str, OutputView]


@dataclass(frozen=True)
class UniverseView:
    """The stack as it is in one of the root's universes."""

    root: str  # the root's astra.yaml, as a Location's `file` names it
    universe: str  # the universe's id
    analyses: tuple[AnalysisView, ...]

    def to_json(self) -> dict[str, Any]:
        """The view as `astra-universe-view/1` (design §4.11)."""
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
        "outputs": {id_: {"result": _result(output)} for id_, output in analysis.outputs.items()},
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
    assert selection is not None  # every universe of a valid stack has one (design §4.13 case 7)
    built = context.building.universes[element]
    analyses: list[AnalysisView] = []
    for member, analysis in stack.determined():
        decisions: dict[str, DecisionView] = {}
        for id_ in analysis.decisions:
            decision = Element(member.identity, "decision", id_)
            selected = min(selection.options(decision), default=None)
            decisions[id_] = DecisionView(selected)
        outputs: dict[str, OutputView] = {}
        for id_ in analysis.outputs:
            output = Element(member.identity, "output", id_)
            at = element if output in context.per_universe else None
            result = context.building.planned.get((output, at))
            found = () if result is None else places(stack, result)
            outputs[id_] = OutputView(result, found)
        analyses.append(
            AnalysisView(
                member,
                member.identity in built,
                MappingProxyType(decisions),
                MappingProxyType(outputs),
            )
        )
    return UniverseView(stack.analyses[stack.root].file, universe, tuple(analyses))
