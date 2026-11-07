"""Environments: the extension point through which a runner's package says what an environment
it records holds, and whether it can be recreated (§19, §21, design §4.10).

A record names the environment its recipe ran in by an IRI, enough for its runner to recreate it
(§19), and a runner should let someone see what it holds (§21). astra-tools knows no scheme of
IRIs itself: another package registers an object that has `Scheme`'s members in the entry-point
group `astra.environments`, and the check report shows what each registered scheme answered for
each record's environment.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

GROUP = "astra.environments"
"""The entry-point group other packages register their schemes in (design §4.10)."""


class Scheme(Protocol):
    """A kind of environment IRI a runner records (§19)."""

    @property
    def name(self) -> str:
        """The scheme's name, as the check report gives it."""
        ...

    def recognises(self, iri: str) -> bool:
        """Whether `iri` is one of this scheme's."""
        ...

    def holds(self, iri: str) -> str:
        """What the environment `iri`, which it recognises, holds, as text of its own."""
        ...

    def recreatable(self, iri: str) -> bool:
        """Whether the environment `iri`, which it recognises, can be recreated."""
        ...


@dataclass(frozen=True)
class Answer:
    """What a scheme answered for an environment IRI it recognises."""

    scheme: str  # its name
    holds: str
    recreatable: bool


def registered() -> tuple[Scheme, ...]:
    """Each scheme another package registers in `GROUP`; there is no built-in one."""
    from importlib.metadata import entry_points

    return tuple(point.load() for point in entry_points(group=GROUP))


def answers(iri: str, schemes: Iterable[Scheme]) -> tuple[Answer, ...]:
    """What each of `schemes` that recognises `iri` answers for it, in their order."""
    return tuple(
        Answer(scheme.name, scheme.holds(iri), scheme.recreatable(iri))
        for scheme in schemes
        if scheme.recognises(iri)
    )
