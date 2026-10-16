"""Universes declared in an analysis and what each one selects.

A universe is declared in its analysis's ``universes`` list - in full or as
a diff of another universe of the same analysis (``derived_from``). The
validator, the resolver and the CLI all need to know what a universe selects
once its ``derived_from`` chain is followed. That is its *effective
selection* and it is worked out here.

Three rules give the effective selection:

- the base's effective selection comes first and the universe's own
  ``decisions`` are written over it;
- ``analyses`` entries are inherited per sub-analysis in the same way, but an
  entry that names a ``universe`` replaces the inherited entry;
- a selection inherited for a decision whose ``when`` no longer holds is
  dropped. A selection the universe makes itself is kept so the validator
  can report it as inactive.

As in ``astra.resolve`` the input is assumed to be valid. An unknown
``derived_from`` or a loop gives ``None`` rather than an exception and
``astra.validation.semantic`` reports it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from astra.helpers import Scope, _collect_node_decisions, is_condition_met

__all__ = [
    "EffectiveUniverse",
    "declared_universes",
    "derived_from_chain",
    "effective_universe",
]


@dataclass(frozen=True)
class EffectiveUniverse:
    """A universe with its ``derived_from`` chain followed.

    ``selection`` is shaped like a universe (``decisions`` and ``analyses``)
    and is complete. ``inherited`` holds the qualified ids of the decisions
    whose selection came from a base universe rather than from this one, e.g.
    ``classification.classifier``.
    """

    id: str
    selection: dict[str, Any]
    inherited: frozenset[str]


def declared_universes(node: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The universes *node* declares, by id.

    If an id is declared twice the first one wins - the validator reports the
    duplicate.
    """
    result: dict[str, dict[str, Any]] = {}
    for universe in node.get("universes") or []:
        if not isinstance(universe, dict):
            continue
        universe_id = universe.get("id")
        if isinstance(universe_id, str) and universe_id not in result:
            result[universe_id] = universe
    return result


def derived_from_chain(
    universes: Mapping[str, Mapping[str, Any]], universe_id: str
) -> list[str] | None:
    """*universe_id* followed by each universe it derives from, in order.

    Returns ``None`` if an id in the chain isn't declared or the chain loops.
    """
    chain: list[str] = []
    current: str | None = universe_id
    while current is not None:
        if current not in universes or current in chain:
            return None
        chain.append(current)
        base = universes[current].get("derived_from")
        current = str(base) if base else None
    return chain


def effective_universe(node: Mapping[str, Any], universe_id: str) -> EffectiveUniverse | None:
    """The effective selection of a universe declared on *node*.

    Args:
        node: The analysis that declares the universe, with its external
            (``path:``) sub-analyses already resolved.
        universe_id: The universe's id.

    Returns:
        The effective universe - or ``None`` if the id isn't declared on
        *node* or its ``derived_from`` chain can't be followed.
    """
    universes = declared_universes(node)
    chain = derived_from_chain(universes, universe_id)
    if chain is None:
        return None

    merged: dict[str, Any] = {}
    for link in reversed(chain):
        merged = _merge(merged, universes[link])

    own = _qualified_decisions(universes[universe_id], ())
    selection = _drop_inactive_inherited(node, merged, own, (), {})
    selection["id"] = universe_id
    return EffectiveUniverse(
        id=universe_id,
        selection=selection,
        inherited=frozenset(_qualified_decisions(selection, ()) - own),
    )


def _merge(base: Mapping[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    """Writes *over*'s selections over *base*'s and returns a new universe dict.

    An entry that names a ``universe`` stands for that universe as a whole so
    it isn't merged with the entry on the other side.
    """
    decisions = {**(base.get("decisions") or {}), **(over.get("decisions") or {})}
    base_subs: Mapping[str, Any] = base.get("analyses") or {}
    over_subs: Mapping[str, Any] = over.get("analyses") or {}
    analyses: dict[str, Any] = {}
    for sub_id in (*base_subs, *(k for k in over_subs if k not in base_subs)):
        inherited = base_subs.get(sub_id)
        own = over_subs.get(sub_id)
        if not isinstance(own, Mapping):
            analyses[sub_id] = dict(inherited) if isinstance(inherited, Mapping) else inherited
        elif not isinstance(inherited, Mapping) or own.get("universe") or inherited.get("universe"):
            analyses[sub_id] = dict(own)
        else:
            analyses[sub_id] = _merge(inherited, own)
    result: dict[str, Any] = {"decisions": decisions}
    if analyses:
        result["analyses"] = analyses
    return result


def _qualified_decisions(universe: Mapping[str, Any], scope: Scope) -> set[str]:
    """Every decision *universe* selects, by qualified id.

    An ``analyses`` entry that names a ``universe`` adds nothing - its
    selections belong to that universe.
    """
    result = {".".join((*scope, str(d))) for d in (universe.get("decisions") or {})}
    for sub_id, sub in (universe.get("analyses") or {}).items():
        if isinstance(sub, Mapping) and not sub.get("universe"):
            result |= _qualified_decisions(sub, (*scope, str(sub_id)))
    return result


def _drop_inactive_inherited(
    node: Mapping[str, Any],
    universe: Mapping[str, Any],
    own: set[str],
    scope: Scope,
    above: Mapping[str, str],
) -> dict[str, Any]:
    """Drops inherited selections whose decision's ``when`` no longer holds.

    *above* holds the selections made above *node* (flattened) - that's what
    the validator evaluates a ``when`` against. Dropping one selection can
    switch off another decision so this repeats until nothing changes.
    """
    declared = _collect_node_decisions(dict(node))
    decisions = {str(k): str(v) for k, v in (universe.get("decisions") or {}).items()}
    changed = True
    while changed:
        changed = False
        for decision_id in list(decisions):
            if ".".join((*scope, decision_id)) in own:
                continue
            when = (declared.get(decision_id) or {}).get("when")
            if when and not is_condition_met(when, {**above, **decisions}):
                del decisions[decision_id]
                changed = True

    result: dict[str, Any] = {"decisions": decisions}
    sub_nodes: Mapping[str, Any] = node.get("analyses") or {}
    analyses: dict[str, Any] = {}
    for sub_id, sub in (universe.get("analyses") or {}).items():
        sub_node = sub_nodes.get(sub_id)
        if isinstance(sub, Mapping) and not sub.get("universe") and isinstance(sub_node, Mapping):
            analyses[sub_id] = _drop_inactive_inherited(
                sub_node, sub, own, (*scope, str(sub_id)), {**above, **decisions}
            )
        else:
            analyses[sub_id] = sub
    if analyses:
        result["analyses"] = analyses
    return result
