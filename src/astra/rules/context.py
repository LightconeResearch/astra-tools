"""What every validator rule is a function of (design §4.4).

A `Context` holds the Stack and what `universes.py` derives from it, each computed once, as a
`cached_property` of the Context, and the predicates of design §4.13 that the rules consult before
reporting: a rule on an undetermined subject isn't reported anywhere.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property

from astra import universes
from astra.diagnostics import Catalogue, Diagnostic, Location
from astra.stack import Element, Identity, Pointer, Resolution, Stack
from astra.universes import Building, Chain, Selection


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
        return universes.selections(self.stack, self.written)

    @cached_property
    def driven(self) -> Mapping[Identity, tuple[Chain, ...]]:
        """The chains of declarations each analysis's universes drive (§16)."""
        return universes.driven(self.stack)

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
        """What each output depends on directly (§10)."""
        return universes.depends(self.stack)

    @cached_property
    def cycles(self) -> frozenset[Element]:
        """The outputs that depend on themselves (§10)."""
        return universes.cycles(self.depends)

    @cached_property
    def written(self) -> Mapping[Element, tuple[Resolution, ...]]:
        """The addresses each decision and output writes."""
        return universes.written(self.stack)

    @cached_property
    def building(self) -> Building:
        """The universes built, and the root's planned results (§16, §18)."""
        return universes.building(
            self.stack, self.written, self.selections, self.driven, self.pins, self.per_universe
        )

    # --- design §4.13 ---

    def names_nothing(self, resolution: Resolution) -> bool:
        """design §4.13 cases 4 and 5: an address that doesn't resolve, or that goes through a
        declaration whose analysis is undetermined, names nothing, and no rule is checked on
        what it would name."""
        return resolution.element is None

    def on_cycle(self, element: Element | None) -> bool:
        """design §4.13 case 13: whether `element` is an output on a cycle, on whose results'
        places, and on what reads it, no rule but `OUTPUT_CYCLE` is checked."""
        return element in self.cycles

    def activity(self, universe: Element, element: Element) -> bool | None:
        """design §4.13 cases 6 and 7: whether a decision or an output is active in `universe`
        (§9); None where its activity is undetermined, or the universe has no effective
        selection."""
        selection = self.selections[universe]
        return None if selection is None else selection.active(element)


def _listed(items: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
