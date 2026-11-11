"""What every validator rule is a function of (design §4.4).

A `Context` holds the Stack and what `universes.py` derives from it, each computed once, as a
`cached_property` of the Context, and the predicates of design §4.13 that the rules consult before
reporting: a rule on an undetermined subject isn't reported anywhere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property
from types import MappingProxyType

from astra import universes
from astra.diagnostics import Catalogue, Diagnostic, Location
from astra.stack import Element, Identity, Pointer, Resolution, Stack
from astra.universes import Building, Chain, Run, Selection, built, own_universes


@dataclass(frozen=True)
class Context:
    stack: Stack
    catalogue: Catalogue

    def at(self, identity: Identity, pointer: Pointer, key: str | None = None) -> Location:
        """Where `pointer`, and its key `key`, are in `identity`'s file."""
        return self.stack.location(identity, pointer, key)

    def diagnostic(
        self, code: str, message: str, location: Location, related: Iterable[Location] = ()
    ) -> Diagnostic:
        """A diagnostic for `code`, at its rule's level (§4)."""
        return self.catalogue.diagnostic(code, message, location, related)

    def named(self, universes: Iterable[Element], file: Identity) -> str:
        """Universes as a message about `file` names them: `u1` and `u2` for its analysis's own,
        and `v1` of `subanalysis` for those of the analysis in another folder."""
        by_analysis: dict[Identity, list[str]] = {}
        for universe in universes:
            by_analysis.setdefault(universe.analysis, []).append(f"`{universe.id}`")
        each = [
            _listed(ids) if analysis == file else f"{_listed(ids)} of `{analysis}`"
            for analysis, ids in by_analysis.items()
        ]
        return _listed(each)

    # --- what universes.py derives ---

    @cached_property
    def selections(self) -> Mapping[Element, Selection | None]:
        """Every universe's effective selection (§12), None where it has none (design §4.13
        case 7)."""
        return universes.selections(self.stack)

    @cached_property
    def imports(self) -> Mapping[tuple[Identity, str], Element | None]:
        """The universe each import names, by its file's analysis and its id (§12)."""
        return universes.imports(self.stack)

    @cached_property
    def pins(self) -> Mapping[Resolution, Element | None]:
        """The universe each pin names (§16 *Pins and imported universes*)."""
        return universes.pins(self.stack, self.imports)

    @cached_property
    def per_universe(self) -> frozenset[Element]:
        """The outputs built per universe (§13)."""
        return universes.per_universe(self.stack)

    @cached_property
    def depends(self) -> universes.Depends:
        """What each output and switch depends on directly (§10)."""
        return universes.depends(self.stack)

    @cached_property
    def cycles(self) -> frozenset[Element]:
        """The outputs and switches that depend on themselves (§10)."""
        return universes.cycles(self.depends)

    @cached_property
    def written(self) -> Mapping[Element, tuple[Resolution, ...]]:
        """The addresses each decision, output and switch writes."""
        return universes.written(self.stack)

    @cached_property
    def meaning(self) -> universes.Meaning:
        """What each switch takes, and whether each element is built, in each universe (Elements
        *takes*, Results *built*)."""
        return universes.Meaning(
            self.stack, self.written, self.selections, self.pins, self.per_universe, self.cycles
        )

    @cached_property
    def runs(self) -> Mapping[Identity, Run]:
        """For each analysis of the stack, what it reaches, plans and uses with itself driving
        (Results *uses*): each analysis's own universes are judged on its own run."""
        return MappingProxyType(
            {
                member.identity: universes.run(
                    self.stack,
                    self.meaning,
                    self.written,
                    self.selections,
                    self.pins,
                    self.per_universe,
                    self.cycles,
                    member.identity,
                )
                for member, _ in self.stack.determined()
            }
        )

    @cached_property
    def driven(self) -> Mapping[Identity, tuple[Chain, ...]]:
        """The chains of declarations each analysis's universes drive (§16; Elements): through a
        declaration with no key where none of its analysis's decisions is used, or may be, in
        a universe of the analysis driving."""
        return universes.driven(self.stack, self._used, self._maybe)

    @cached_property
    def unsettled(self) -> Mapping[Identity, frozenset[Chain]]:
        """For each analysis driving, the chains whose driving is undetermined (design §4.13 case
        6, *undetermined driving*)."""
        return universes.unsettled(self.stack, self._used, self._maybe)

    @cached_property
    def _used(self) -> universes.Used:
        return self._over_universes(lambda run: run.used)

    @cached_property
    def _maybe(self) -> universes.Used:
        return self._over_universes(lambda run: run.maybe)

    def _over_universes(
        self, field: Callable[[Run], Mapping[Element, frozenset[Element]]]
    ) -> universes.Used:
        """For each analysis, the union of `field` of its run over its own universes."""
        found: dict[Identity, frozenset[Element]] = {}
        for identity, run in self.runs.items():
            each = field(run)
            found[identity] = frozenset().union(
                *(
                    each.get(universe, frozenset())
                    for universe in own_universes(self.stack, identity)
                )
            )
        return MappingProxyType(found)

    @cached_property
    def building(self) -> Building:
        """What the root reaches and plans, the universes built, and its planned results whose
        analysis is built in their universe (§16, §18)."""
        return universes.building(self.stack, self.runs[self.stack.root], self.driven)

    def used(self, universe: Element) -> frozenset[Element]:
        """The decisions `universe` uses, with its own analysis driving (Results *uses*)."""
        run = self.runs.get(universe.analysis)
        return frozenset() if run is None else run.used.get(universe, frozenset())

    def maybe(self, universe: Element) -> frozenset[Element]:
        """The decisions whose use in `universe`, with its own analysis driving, is undetermined
        (design §4.13 case 6)."""
        run = self.runs.get(universe.analysis)
        return frozenset() if run is None else run.maybe.get(universe, frozenset())

    def built(self, element: Element, universe: Element | None) -> bool | None:
        """Whether `element` is built in `universe` (Results *built*; `Meaning.built`)."""
        return self.meaning.built(element, universe)

    def unsettled_in(self, universe: Element) -> frozenset[Identity]:
        """The analyses that a universe's analysis's universes reach only through a chain whose
        driving is undetermined, and the analyses those declare, directly or not (design §4.13
        case 6): whether they are built in `universe` is undetermined."""
        return self._unsettled_in.get(universe.analysis, frozenset())

    @cached_property
    def _unsettled_in(self) -> Mapping[Identity, frozenset[Identity]]:
        found: dict[Identity, frozenset[Identity]] = {}
        for identity, chains in self.unsettled.items():
            reached: set[Identity] = set()
            todo = [chain[-1].reached for chain in chains]
            while todo:
                current = todo.pop()
                if current is None or current in reached:
                    continue
                reached.add(current)
                todo.extend(d.reached for d in self.stack.analyses[current].declarations.values())
            found[identity] = frozenset(reached - set(built(self.driven[identity], identity)))
        return MappingProxyType(found)

    def unsettled_through(self, entry: Resolution) -> bool:
        """Whether `entry`'s chain of declarations goes through one whose driving, from its own
        file, is undetermined (design §4.13 case 6)."""
        chains = self.unsettled.get(entry.file, frozenset())
        return any(entry.chain[:end] in chains for end in range(1, len(entry.chain) + 1))

    # --- design §4.13 ---

    def names_nothing(self, resolution: Resolution) -> bool:
        """design §4.13 cases 4 and 5: an address that doesn't resolve, or that goes through a
        declaration whose analysis is undetermined, names nothing, and no rule is checked on
        what it would name."""
        return resolution.element is None

    def on_cycle(self, element: Element | None) -> bool:
        """design §4.13 case 13: whether `element` is an output or a switch on a cycle, on whose
        results' places, and on what reads it, no rule but `OUTPUT_CYCLE` is checked."""
        return element in self.cycles


def _listed(items: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
