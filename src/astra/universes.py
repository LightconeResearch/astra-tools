"""What each universe selects, what is active, driven and built in it, and what is planned
(§9, §12, §13, §16, §18; design §2).

Pure functions of a Stack, each of which `rules.Context` computes once:

- `selections`: every universe's effective selection (§12), with the activity of every decision
  and output of the stack in it (§9; design §4.13 cases 6 and 7);
- `driven`: the chains of declarations each analysis's universes drive (§16 *Driving*; design §4.13
  case 10), and `built`, the analyses built in its universes, whose decisions they set, each
  with the chains that reach it;
- `imports` and `pins`: the universe each import and each pin names (§16 *Pins and imported
  universes*);
- `per_universe`: the outputs built per universe, every other being built once (§13);
- `depends` and `cycles`: what each output depends on directly, and the outputs that depend on
  themselves (§10);
- `building`: the universes built, what is built in each, the root's planned results, each with
  its names, and the universe each entry they read is read in (§16 *The universe being built*,
  §18); `places`, where each name of a planned result puts its record and its bytes (§18
  *Where records and bytes go*).

A universe is named by its analysis and its id (§16 *The universe being built*): an `Element` of
kind `universe`, so imports of one universe, under any ids, name one Element.
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from astra import model
from astra.stack import Declaration, Element, Identity, Resolution, Stack

Chain = tuple[Declaration, ...]
"""Declarations from one analysis's file, each in the file of the analysis the one before reaches
(§15): an address's, or a key's, as far as they resolve."""


@dataclass(frozen=True)
class Selection:
    """A universe's effective selection (§12 *The effective selection*), and what is active in
    it (§9)."""

    universe: Element
    entries: tuple[Resolution, ...]  # the keys it selects, own and inherited, each where written
    inherited: tuple[Resolution, ...]  # the effective selection it derives from; () without one
    activity: Mapping[Element, bool | None]  # each decision and output of the stack

    def own(self, entry: Resolution) -> bool:
        """Whether the universe sets `entry` itself, rather than inherits it."""
        return entry.owner == self.universe

    def options(self, decision: Element) -> frozenset[str]:
        """The options selected for `decision`, under any of its spellings."""
        return frozenset(
            entry.option
            for entry in self.entries
            if entry.element == decision and entry.option is not None
        )

    def active(self, element: Element) -> bool | None:
        """Whether a decision or an output is active here (§9); None where that is undetermined
        (design §4.13 case 6)."""
        return self.activity.get(element)


def options(stack: Stack, decision: Element) -> Mapping[str, model.Option]:
    """The options of `decision`, a decision of an analysis whose file is valid."""
    return stack.analysis(decision.analysis).decisions[decision.id].options


def when(stack: Stack, element: Element) -> tuple[str, ...]:
    """The conditions of a decision's or an output's `when`, as written."""
    analysis = stack.analysis(element.analysis)
    if element.kind == "decision":
        return analysis.decisions[element.id].when
    return analysis.outputs[element.id].when


def names_option(stack: Stack, resolution: Resolution) -> bool:
    """Whether a condition, a constraint or a selection names an option: its address resolves to
    a decision, and its option is one of that decision's (design §4.13 case 5)."""
    decision = resolution.element
    return decision is not None and resolution.option in options(stack, decision)


def own_keys(stack: Stack, universe: Element) -> tuple[Resolution, ...]:
    """The keys of `universe`'s own `decisions`, each resolved where it is written."""
    return tuple(
        resolution
        for resolution in stack.resolutions
        if resolution.field == "selection" and resolution.owner == universe
    )


# --- §12: effective selections ---


def selections(
    stack: Stack, written: Mapping[Element, tuple[Resolution, ...]]
) -> Mapping[Element, Selection | None]:
    """The effective selection of every universe of every analysis of the stack, a driven
    analysis's own included (§16 *What a validator checks*), from the addresses each decision
    and output writes (`written`); None for a universe that has none (design §4.13 case 7)."""
    whens = {
        element: tuple(entry for entry in entries if entry.field == "when")
        for element, entries in written.items()
    }
    found: dict[Element, Selection | None] = {}
    for member, analysis in stack.determined():
        for id_, universe in analysis.universes.items():
            if not universe.is_import:
                element = Element(member.identity, "universe", id_)
                effective_selection(stack, element, whens, found)
    return MappingProxyType(found)


def effective_selection(
    stack: Stack,
    universe: Element,
    whens: Mapping[Element, tuple[Resolution, ...]],
    found: dict[Element, Selection | None],
    deriving: tuple[Element, ...] = (),
) -> Selection | None:
    """§12's three steps for `universe`, or None where its `derived_from` doesn't name another
    of its analysis's universes, or its chain loops or reaches a universe with no effective
    selection (design §4.13 case 7). `found` holds the selections already made, and `deriving` the
    universes waiting on this one's."""
    if universe in found:
        return found[universe]
    analysis = stack.analysis(universe.analysis)
    own = own_keys(stack, universe)
    named = analysis.universes[universe.id].derived_from
    result: Selection | None = None
    if named is None:  # step 1
        result = Selection(universe, own, (), _activity(stack, whens, own))
    else:
        parent = Element(universe.analysis, "universe", named)
        entry = analysis.universes.get(named)
        if entry is not None and not entry.is_import and parent not in (*deriving, universe):
            inherited = effective_selection(stack, parent, whens, found, (*deriving, universe))
            if inherited is not None:
                result = _derive(stack, whens, universe, own, inherited.entries)
    found[universe] = result
    return result


def _derive(
    stack: Stack,
    whens: Mapping[Element, tuple[Resolution, ...]],
    universe: Element,
    own: tuple[Resolution, ...],
    inherited: tuple[Resolution, ...],
) -> Selection:
    """Steps 2 and 3: each own selection replaces what is inherited for its decision, and an
    inherited selection of a decision that isn't active in the result is dropped. One whose
    activity is undetermined isn't (design §4.13 case 6)."""
    kept = tuple(entry for entry in inherited if not any(_one_key(entry, mine) for mine in own))
    activity = _activity(stack, whens, (*kept, *own))  # OPEN(O2): step 3 is one pass
    kept = tuple(
        entry for entry in kept if entry.element is None or activity[entry.element] is not False
    )
    entries = (*kept, *own)
    return Selection(universe, entries, inherited, _activity(stack, whens, entries))


def _one_key(inherited: Resolution, own: Resolution) -> bool:
    """Whether an own selection replaces an inherited one: one key, or two spellings of one
    decision (§16 *What a universe sets*)."""
    same = own.element is not None and own.element == inherited.element
    return same or inherited.key == own.key


# --- §9: activity ---


def written(stack: Stack) -> Mapping[Element, tuple[Resolution, ...]]:
    """The addresses each decision and output of the stack's valid files writes, () for none: an
    output's `inputs`, `decisions` and `when`; a decision's `when` and its options' constraints."""
    found: dict[Element, list[Resolution]] = {}
    for member, analysis in stack.determined():
        for id_ in analysis.decisions:
            found[Element(member.identity, "decision", id_)] = []
        for id_ in analysis.outputs:
            found[Element(member.identity, "output", id_)] = []
    for resolution in stack.resolutions:
        if resolution.owner is not None and resolution.owner.kind in ("output", "decision"):
            found[resolution.owner].append(resolution)
    return MappingProxyType({element: tuple(entries) for element, entries in found.items()})


def _activity(
    stack: Stack,
    whens: Mapping[Element, tuple[Resolution, ...]],
    entries: tuple[Resolution, ...],
) -> Mapping[Element, bool | None]:
    """Whether each decision and output is active in the selection `entries`: each condition
    of its `when` holds (§9). None where a condition is undetermined (design §4.13 case 6): it names
    nothing, or tests a decision that `entries` set to an option that names nothing, or leave
    unset though it isn't inactive."""
    chosen: dict[Element, set[str]] = {}
    for entry in entries:
        if entry.element is not None and entry.option is not None:
            chosen.setdefault(entry.element, set()).add(entry.option)
    found: dict[Element, bool | None] = {}

    def active(element: Element, waiting: frozenset[Element]) -> bool | None:
        if element in waiting:
            return None  # a `when` that waits on its own element
        if element not in found:
            held = [holds(condition, waiting | {element}) for condition in whens[element]]
            found[element] = None if None in held else all(held)
        return found[element]

    def holds(condition: Resolution, waiting: frozenset[Element]) -> bool | None:
        decision = condition.element
        if decision is None or not names_option(stack, condition):
            return None
        selected = chosen.get(decision, set())
        if not selected and active(decision, waiting) is not False:
            return None  # OPEN(O16): unset, and not inactive
        if not selected <= options(stack, decision).keys():
            return None
        return (condition.option in selected) != condition.negated

    return MappingProxyType({element: active(element, frozenset()) for element in whens})


# --- §16: driving ---


def looping(key: Resolution) -> tuple[int, int] | None:
    """The place in `key.chain` of the first declaration that leads back to an analysis already
    on the key's chain, the universe's analysis included (§16 *Driving*), and the place on the
    chain of the analysis it leads back to (0 for the universe's own, `n` for the one the `n`th
    declaration reaches); None where none does, judged up to the first declaration that doesn't
    resolve or whose analysis is undetermined (design §4.13 case 10)."""
    on_chain: list[Identity | None] = [key.file]
    for index, declaration in enumerate(key.chain):
        if declaration.reached in on_chain:
            return index, on_chain.index(declaration.reached)
        if declaration.outcome != "reached":
            return None
        on_chain.append(declaration.reached)
    return None


def unlooped(key: Resolution) -> str:
    """`key` with every stretch of declarations that leads back cut out: `stage.d` for
    `stage.again.d`, where `stage` declares `again: {path: .}` (§16)."""
    ids = (declaration.id for declaration in cut_loops(key.file, key.chain))
    return ".".join((*ids, *key.address.segments[len(key.chain) :]))


def cut_loops(start: Identity, chain: Chain) -> Chain:
    """`chain`, from `start`'s file, with every stretch of declarations that leads back to an
    analysis already on it, `start` included, cut out (§16 *Driving*)."""
    on_chain: list[Identity | None] = [start]
    kept: list[Declaration] = []
    for declaration in chain:
        if declaration.reached in on_chain:
            back = on_chain.index(declaration.reached)
            del on_chain[back + 1 :], kept[back:]
        else:
            on_chain.append(declaration.reached)
            kept.append(declaration)
    return tuple(kept)


def along(result: Planned, chain: Chain) -> int | None:
    """Which of `result`'s names `chain` gives, its index: `chain`'s declarations from the
    analysis it belongs to on, every stretch that leads back cut out (`cut_loops`), are those of
    the name (§20 *Evidence*). None where they give none of its names, as where `chain` never
    reaches that analysis."""
    cut = cut_loops(result.owner, chain)
    return next((index for index, named in enumerate(result.chains) if named == cut), None)


def driven(stack: Stack) -> Mapping[Identity, tuple[Chain, ...]]:
    """The chains of declarations from each analysis's file that its universes drive (§16
    *Which declarations are driven*), each driven on its own:

    - each chain a key goes through, but for a key that loops (design §4.13 case 10). Every key
      of an effective selection is one that a universe sets itself, and every key a universe
      sets is in its effective selection or counts in its place (case 7): so the keys that
      drive are those of the universes' own `decisions`;
    - and a driven chain, the empty one of the analysis's own file included, followed by a
      declaration of an analysis with no decisions that leads back to no analysis already on it.

    An undetermined analysis's declarations aren't known, so none are driven (design §4.13 case 4).
    """
    found: dict[Identity, tuple[Chain, ...]] = {}
    for member, _ in stack.determined():
        chains: dict[Chain, None] = {}
        for key in stack.resolutions:
            if key.field == "selection" and key.file == member.identity and looping(key) is None:
                # through the declarations it resolves, whatever its last id names (design
                # §4.13 case 5)
                for end in range(1, len(key.chain) + 1):
                    chains[key.chain[:end]] = None
        todo: list[Chain] = [(), *chains]
        while todo:
            chain = todo.pop(0)
            folder = chain[-1].reached if chain else member.identity
            if folder is None or (chain and chain[-1].outcome != "reached"):
                continue
            on_chain = (member.identity, *(declaration.reached for declaration in chain))
            for declaration in stack.analyses[folder].declarations.values():
                longer = (*chain, declaration)
                if (
                    declaration.outcome == "reached"
                    and declaration.reached not in on_chain
                    and not _has_decisions(stack, declaration)
                    and longer not in chains
                ):
                    chains[longer] = None
                    todo.append(longer)
        found[member.identity] = tuple(chains)
    return MappingProxyType(found)


def _has_decisions(stack: Stack, declaration: Declaration) -> bool:
    """Whether the analysis `declaration` reaches has decisions, or may have: an undetermined
    one's aren't known."""
    analysis = None if declaration.reached is None else stack.analyses[declaration.reached].analysis
    return analysis is None or bool(analysis.decisions)


def built(chains: tuple[Chain, ...], driver: Identity) -> Mapping[Identity, tuple[Chain, ...]]:
    """The analyses built in a universe of `driver`, whose active decisions every one of its
    universes sets (§16 *What a universe sets*, *The universe being built*), each with the
    chains that reach it: the driver itself, by the empty chain, and each analysis reached
    through a declaration its universes drive, by each such chain of `chains`, in their order.
    An undetermined analysis is left out (design §4.13 case 4)."""
    found: dict[Identity, list[Chain]] = {driver: [()]}
    for chain in chains:
        last = chain[-1]
        if last.outcome == "reached" and last.reached is not None:
            found.setdefault(last.reached, []).append(chain)
    return MappingProxyType({identity: tuple(reaching) for identity, reaching in found.items()})


# --- §16: pins and imported universes ---


def imports(stack: Stack) -> Mapping[tuple[Identity, str], Element | None]:
    """The universe each import names, by the analysis whose file holds it and its id: one of
    another analysis's universes, found by identity (§12 *Imports*, §16); None where it names
    nothing (design §4.13 case 5)."""
    found: dict[tuple[Identity, str], Element | None] = {}
    for resolution in stack.resolutions:
        if resolution.field == "import":
            assert resolution.owner is not None  # the entry of `universes` that holds it
            found[resolution.file, resolution.owner.id] = resolution.element
    return MappingProxyType(found)


def pins(
    stack: Stack, imported: Mapping[tuple[Identity, str], Element | None]
) -> Mapping[Resolution, Element | None]:
    """The universe each pin names, resolved in the file it is written in (§16 *Pins and
    imported universes*): the entry of the file's `universes` with its id, a universe or the one
    an import names, or else the universe with its id of the analysis whose element the
    reference names. None where it names none (`UNKNOWN_PIN_UNIVERSE`), or names an import that
    names nothing, or its reference names nothing (design §4.13 case 5)."""
    found: dict[Resolution, Element | None] = {}
    for resolution in stack.resolutions:
        if resolution.pin is None:
            continue
        entry = stack.analysis(resolution.file).universes.get(resolution.pin)
        named: Element | None = None
        if entry is not None and entry.is_import:
            named = imported[resolution.file, resolution.pin]
        elif entry is not None:
            named = Element(resolution.file, "universe", resolution.pin)
        elif resolution.element is not None:
            target = stack.analysis(resolution.element.analysis).universes.get(resolution.pin)
            if target is not None and not target.is_import:
                named = Element(resolution.element.analysis, "universe", resolution.pin)
        found[resolution] = named
    return MappingProxyType(found)


# --- §13: built per universe or built once ---


def per_universe(stack: Stack) -> frozenset[Element]:
    """The outputs built per universe (§13 *Built per universe or built once*): each that lists
    `decisions`, has a `when`, or has an unpinned entry of `inputs` naming an output built per
    universe, through any declaration. Every other output is built once. An entry that names
    nothing names no output (design §4.13 case 5)."""
    found = {
        Element(member.identity, "output", id_)
        for member, analysis in stack.determined()
        for id_, output in analysis.outputs.items()
        if output.decisions or output.when
    }
    reads = [entry for entry in stack.resolutions if entry.field == "inputs" and entry.pin is None]
    grown = True
    while grown:
        grown = False
        for entry in reads:
            if entry.element in found and entry.owner not in found:
                assert entry.owner is not None  # the output whose `inputs` holds it
                found.add(entry.owner)
                grown = True
    return frozenset(found)


Depends = Mapping[Element, tuple[tuple[Element, Resolution], ...]]
"""What each output reads through `Output.inputs`: each output an entry names, with the entry."""


def depends(stack: Stack) -> Depends:
    """What each output depends on directly (§10): each output an entry of its `inputs` names,
    pinned or not, through any declaration, known by its analysis's identity. An entry that
    names nothing names no output (design §4.13 cases 4 and 5)."""
    found: dict[Element, list[tuple[Element, Resolution]]] = {}
    for entry in stack.resolutions:
        if entry.field == "inputs" and entry.element is not None:
            if entry.element.kind == "output":
                assert entry.owner is not None  # the output whose `inputs` holds it
                found.setdefault(entry.owner, []).append((entry.element, entry))
    return MappingProxyType({owner: tuple(entries) for owner, entries in found.items()})


def cycles(depends: Depends) -> frozenset[Element]:
    """The outputs that depend on themselves, directly or through others (§10)."""
    found = set()
    for start in depends:
        seen, todo = set(), [read for read, _ in depends[start]]
        while todo:
            current = todo.pop()
            if current == start:
                found.add(start)
                break
            if current not in seen:
                seen.add(current)
                todo.extend(read for read, _ in depends.get(current, ()))
    return frozenset(found)


# --- §16 and §18: the universes built, and the planned results ---


@dataclass(frozen=True)
class Planned:
    """A planned result (§18): its output's, in the universe it is built in or, for an output
    built once, once; and, for each of its names, the driven declarations to the output's
    analysis from the analysis it belongs to, the universe's (§18 *Which analysis a
    result belongs to, and its name*)."""

    output: Element
    universe: Element | None  # None for an output built once
    chains: tuple[Chain, ...]

    @property
    def names(self) -> tuple[str, ...]:
        """Its names: the output's id after the ids of each chain's declarations."""
        return tuple(
            ".".join((*(declaration.id for declaration in chain), self.output.id))
            for chain in self.chains
        )

    @property
    def owner(self) -> Identity:
        """The analysis it belongs to (§18): the universe's, whichever file pins it, or, for an
        output built once, its output's."""
        return self.output.analysis if self.universe is None else self.universe.analysis


@dataclass(frozen=True)
class Place:
    """Where one name of a planned result puts it (§18 *Where records and bytes go*): each path
    from the top of the tree its owner is read in (§17 *Identity*), in the owner's folder."""

    name: str
    address: str  # the name, then `#` and the universe's own id for a result built in one
    record: str  # .astra/records/{universe}/{name}.json, or .astra/records/{name}.json
    bytes: str  # the default place: results/{universe}/{name}.{format}, or results/{name}.{format}


def places(stack: Stack, result: Planned) -> tuple[Place, ...]:
    """`result`'s places, one for each of its names, in their order. The universe in a place is
    always the universe's own id, never an import's."""
    format_ = stack.analysis(result.output.analysis).outputs[result.output.id].format
    universe = () if result.universe is None else (result.universe.id,)
    folder = result.owner.folder
    return tuple(
        Place(
            name,
            "#".join((name, *universe)),
            posixpath.join(folder, ".astra", "records", *universe, f"{name}.json"),
            posixpath.join(folder, "results", *universe, f"{name}.{format_}"),
        )
        for name in result.names
    )


def read_in(
    entry: Resolution,
    universe: Element | None,
    pinned: Mapping[Resolution, Element | None],
    per_universe: frozenset[Element],
) -> Element | None:
    """The universe in which an entry of `inputs`, or evidence, that names an output reads it,
    from a result built in `universe` or once (§13 *Pins*): for an
    output built per universe, the one its pin names (`pins`), or else `universe`; None for an
    output built once, whose one result is read pinned or not, and for a pin that names
    nothing."""
    if entry.element not in per_universe:
        return None
    return universe if entry.pin is None else pinned[entry]


@dataclass(frozen=True)
class Building:
    """What building the root builds (§16 *The universe being built*, §18)."""

    universes: Mapping[Element, Mapping[Identity, tuple[Chain, ...]]]
    """Each universe built, the root's first, with the analyses built in it: its driver, the
    analysis whose universe it is, by the empty chain, then each its driver's universes drive,
    by the chains that reach it (`built`)."""
    planned: Mapping[tuple[Element, Element | None], Planned]
    """Each planned result, by its output and universe, in the order reached."""
    considered: tuple[tuple[Element, Element], ...]
    """Each output and universe where the output's result is planned, or would be if its `when`
    held."""
    reads: tuple[tuple[Resolution, Element | None], ...]
    """Each entry of a planned result's `inputs`, and of the root's evidence, that names an
    output, with the universe it reads that output in: the result's, or the one its pin names;
    None for an output built once. A pin that names no universe reads nothing."""


def building(
    stack: Stack,
    written: Mapping[Element, tuple[Resolution, ...]],
    selections: Mapping[Element, Selection | None],
    chains: Mapping[Identity, tuple[Chain, ...]],
    pinned: Mapping[Resolution, Element | None],
    per_universe: frozenset[Element],
    requested: tuple[Element, ...] = (),
) -> Building:
    """The universes built and the root's planned results (§16 *The universe being built*,
    §18), from the addresses each output writes (`written`), the effective selections, the
    chains each analysis's universes drive (`driven`), the universe each pin names (`pins`) and
    the outputs built per universe, with the outputs `requested` planned as the root's own are,
    to build them on request (`plan.plan`):

    - the root's universes are built, and each universe a pin on an output built per universe
      names, in the `inputs` of a planned result's output or in the root's evidence;
    - each output of the root built once has a result, and each built per universe one in each
      of the root's universes where it is active;
    - so has what a planned result's output reads, pinned or not, through any declaration;
    - and what the root's evidence cites: one result where it is pinned or names an output
      built once, and otherwise the output's in each of the root's universes where it is active
      and its analysis is built (§20 *Evidence*).

    A result is planned in a universe only where its output is active there, which a universe
    with no effective selection decides for none (design §4.13 cases 6 and 7), and where its
    output's analysis is built there. A pin that names no universe builds none (case 5)."""
    root = stack.analysis(stack.root)
    universes: dict[Element, Mapping[Identity, tuple[Chain, ...]]] = {}
    planned: dict[tuple[Element, Element | None], Planned] = {}
    considered: dict[tuple[Element, Element], None] = {}
    reads: dict[tuple[Resolution, Element | None], None] = {}
    todo: list[Planned] = []

    def build(universe: Element) -> Mapping[Identity, tuple[Chain, ...]]:
        if universe not in universes:
            universes[universe] = built(chains[universe.analysis], universe.analysis)
        return universes[universe]

    def plan(output: Element, universe: Element | None) -> None:
        named: tuple[Chain, ...] = ((),)  # a result built once is its output's analysis's
        if universe is not None:
            selection = selections[universe]
            # Not planned, and nothing further (design §4.13 cases 7 and 12).
            if selection is None or output.analysis not in build(universe):
                return
            considered[output, universe] = None
            if selection.active(output) is not True:
                return
            named = build(universe)[output.analysis]
        if (output, universe) not in planned:
            result = Planned(output, universe, named)
            planned[output, universe] = result
            todo.append(result)

    def read(entry: Resolution, universe: Element | None) -> None:
        """What an entry of `inputs`, or evidence, reads (`read_in`)."""
        output = entry.element
        if output is None or output.kind != "output":
            return
        at = read_in(entry, universe, pinned, per_universe)
        if output in per_universe:
            if at is None:
                return
            build(at)
        reads[entry, at] = None
        plan(output, at)

    own = [
        Element(stack.root, "universe", id_) for id_, u in root.universes.items() if not u.is_import
    ]
    for universe in own:
        build(universe)
    every: list[Element | None] = [*own]
    once: list[Element | None] = [None]
    outputs = [Element(stack.root, "output", id_) for id_ in root.outputs]
    for output in (*outputs, *requested):  # one asked for, as the root's own
        for target in every if output in per_universe else once:
            plan(output, target)
    for entry in stack.resolutions:
        if entry.field == "artifact" and entry.file == stack.root:
            unpinned = entry.pin is None and entry.element in per_universe
            for target in every if unpinned else once:
                read(entry, target)
    while todo:
        result = todo.pop(0)
        for entry in written[result.output]:
            if entry.field == "inputs":
                read(entry, result.universe)
    return Building(
        MappingProxyType(universes), MappingProxyType(planned), tuple(considered), tuple(reads)
    )
