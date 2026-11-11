"""What each universe selects, what is driven and built in it, and what is planned
(§12, §13, §16, §18; design §2).

Pure functions of a Stack, each of which `rules.Context` computes once:

- `selections`: every universe's effective selection (§12; design §4.13 case 7);
- `driven`: the chains of declarations each analysis's universes drive (§16 *Driving*; design §4.13
  case 10), and `built`, the analyses built in its universes, whose decisions they set, each
  with the chains that reach it;
- `imports` and `pins`: the universe each import and each pin names (§16 *Pins and imported
  universes*);
- `per_universe`: the outputs built per universe, every other being built once (§13);
- `depends` and `cycles`: what each output depends on directly, and the outputs that depend on
  themselves (§10);
- `Meaning`: whether each output is built in each universe, which never turns on driving
  (Results *result*);
- `run`: what an analysis driving reaches from its planning roots, built or not, the universe
  each address it follows is read in, and what it plans (Results *plans*);
- `building`: of the root's run, the universes built, what is built in each, and the planned
  results whose analysis is built in their universe, each with its names (§16 *The universe
  being built*, §18); `places`, where each name of a planned result puts its record and its
  bytes (§18 *Where records and bytes go*).

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
    """A universe's effective selection (§12 *The effective selection*)."""

    universe: Element
    entries: tuple[Resolution, ...]  # the keys it selects, own and inherited, each where written
    inherited: tuple[Resolution, ...]  # the effective selection it derives from; () without one

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


def options(stack: Stack, decision: Element) -> Mapping[str, model.Option]:
    """The options of `decision`, a decision of an analysis whose file is valid."""
    return stack.analysis(decision.analysis).decisions[decision.id].options


def names_option(stack: Stack, resolution: Resolution) -> bool:
    """Whether a constraint or a selection names an option: its address resolves to a
    decision, and its option is one of that decision's (design §4.13 case 5)."""
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


def selections(stack: Stack) -> Mapping[Element, Selection | None]:
    """The effective selection of every universe of every analysis of the stack, a driven
    analysis's own included (§16 *What a validator checks*); None for a universe that has none
    (design §4.13 case 7)."""
    found: dict[Element, Selection | None] = {}
    for member, analysis in stack.determined():
        for id_, universe in analysis.universes.items():
            if not universe.is_import:
                element = Element(member.identity, "universe", id_)
                effective_selection(stack, element, found)
    return MappingProxyType(found)


def effective_selection(
    stack: Stack,
    universe: Element,
    found: dict[Element, Selection | None],
    deriving: tuple[Element, ...] = (),
) -> Selection | None:
    """§12's steps 1 and 2 for `universe` (step 3 went with `when`), or None where its
    `derived_from` doesn't name another of its analysis's universes, or its chain loops or
    reaches a universe with no effective selection (design §4.13 case 7). `found` holds the
    selections already made, and `deriving` the universes waiting on this one's."""
    if universe in found:
        return found[universe]
    analysis = stack.analysis(universe.analysis)
    own = own_keys(stack, universe)
    named = analysis.universes[universe.id].derived_from
    result: Selection | None = None
    if named is None:  # step 1
        result = Selection(universe, own, ())
    else:
        parent = Element(universe.analysis, "universe", named)
        entry = analysis.universes.get(named)
        if entry is not None and not entry.is_import and parent not in (*deriving, universe):
            inherited = effective_selection(stack, parent, found, (*deriving, universe))
            if inherited is not None:
                result = _derive(universe, own, inherited.entries)
    found[universe] = result
    return result


def _derive(
    universe: Element, own: tuple[Resolution, ...], inherited: tuple[Resolution, ...]
) -> Selection:
    """Step 2: each own selection replaces what is inherited for its decision."""
    kept = tuple(entry for entry in inherited if not any(_one_key(entry, mine) for mine in own))
    return Selection(universe, (*kept, *own), inherited)


def _one_key(inherited: Resolution, own: Resolution) -> bool:
    """Whether an own selection replaces an inherited one: one key, or two spellings of one
    decision (§16 *What a universe sets*)."""
    same = own.element is not None and own.element == inherited.element
    return same or inherited.key == own.key


# --- §6: the addresses each element writes ---


def written(stack: Stack) -> Mapping[Element, tuple[Resolution, ...]]:
    """The addresses each decision and output of the stack's valid files writes, () for none: an
    output's `inputs` and `decisions`; a decision's options' constraints."""
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
    """The analyses built in a universe of `driver`, whose decisions every one of its
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
    `decisions`, or has an unpinned entry of `inputs` naming an output built per universe,
    through any declaration. Every other output is built once. An entry that names nothing names
    no output (design §4.13 case 5)."""
    found = {
        Element(member.identity, "output", id_)
        for member, analysis in stack.determined()
        for id_, output in analysis.outputs.items()
        if output.decisions
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


At = tuple[Element, Element | None]
"""An element and the universe it is in, None for an output built once."""


class Meaning:
    """Whether an output is built in a universe (Results *result*), each answer computed once:
    an input, and an output built once, always are; an output built per universe is where every
    entry of its `inputs` read without a pin is. A pinned entry never makes its reader not built.
    It never consults driving: an output can be built in a universe that doesn't build its
    analysis, and then has no result there (§16 *The universe being built*). One for each
    `rules.Context`."""

    def __init__(
        self,
        written: Mapping[Element, tuple[Resolution, ...]],
        selections: Mapping[Element, Selection | None],
        per_universe: frozenset[Element],
        cycles: frozenset[Element],
    ) -> None:
        self._written = written
        self._selections = selections
        self._per_universe = per_universe
        self._cycles = cycles
        self._built: dict[At, bool | None] = {}

    def built(self, element: Element, universe: Element | None) -> bool | None:
        """Whether `element`, an input or an output, is built in `universe` (None: once). None
        where that is undetermined: for an output on a cycle (design §4.13 case 13), and for one
        built per universe in a universe with no effective selection (case 7), or that reads
        without a pin what names nothing (cases 4 and 5) or what is undetermined."""
        key = (element, universe)
        if key not in self._built:
            self._built[key] = self._judged(element, universe)
        return self._built[key]

    def _judged(self, element: Element, universe: Element | None) -> bool | None:
        if element in self._cycles:
            return None
        if element.kind == "input" or element not in self._per_universe:
            return True
        if universe is None or self._selections.get(universe) is None:
            return None
        found: bool | None = True
        for entry in self._written[element]:
            if entry.field == "inputs" and entry.pin is None:
                read = None if entry.element is None else self.built(entry.element, universe)
                found = _both(found, read)
        return found


def _both(one: bool | None, other: bool | None) -> bool | None:
    """Kleene's and, for what is built or planned: False over None, None over True."""
    if one is False or other is False:
        return False
    return None if one is None or other is None else True


@dataclass(frozen=True)
class Run:
    """What one analysis, driving, reaches and plans (Results *plans*)."""

    driver: Identity
    reached: Mapping[At, None]
    """Each output reached from the driver's planning roots, built there or not, by the universe
    it is reached in, None for an output built once, in the order reached."""
    planned: Mapping[At, bool | None]
    """Each output reached that is planned, in the order reached: True, or None where its
    planning is undetermined (design §4.13 case 12)."""
    reads: tuple[tuple[Resolution, Element | None], ...]
    """Each address the reach follows, with the universe it is read in: each entry of a reached
    output's `decisions`, in the output's universe, and each entry of its `inputs` and of the
    driver's evidence that names an output, in the universe it reads that output in
    (`read_in`), None for an output built once. A pin that names no universe reads nothing."""


def run(
    stack: Stack,
    meaning: Meaning,
    written: Mapping[Element, tuple[Resolution, ...]],
    selections: Mapping[Element, Selection | None],
    pinned: Mapping[Resolution, Element | None],
    per_universe: frozenset[Element],
    cycles: frozenset[Element],
    driver: Identity,
    requested: tuple[Element, ...] = (),
) -> Run:
    """What `driver` reaches and plans (Results *plans*), from what `meaning` says is built, the
    addresses each output writes (`written`), the effective selections, the universe each pin
    names (`pins`), the outputs built per universe and those on a cycle; with the outputs
    `requested` as its own, to build them on request (`plan.plan`).

    Its planning roots are its own outputs and what its evidence cites: an output built once,
    and evidence citing one, once; other pinned evidence in the universe its pin names; any
    other in each of its universes. From an output reached, every entry of its `inputs` that
    names an output reaches that output, in the universe it reads it in (`read_in`), whether
    either is built there or not; but nothing is followed from an output on a cycle (design
    §4.13 case 13), or in a universe with no effective selection (case 7). Reach never consults
    what is built, nor driving.

    A root is planned where it is built, and so is what a planned output reads: each output's
    status, where it is reached through others, is the best of each reader's and its own
    (`_both`), True over None. Not built (False), it isn't planned."""
    analysis = stack.analysis(driver)
    own = [
        Element(driver, "universe", id_)
        for id_, universe in analysis.universes.items()
        if not universe.is_import
    ]
    reached: dict[At, None] = {}
    reads: dict[tuple[Resolution, Element | None], None] = {}
    edges: dict[At, list[At]] = {}
    roots: list[At] = []
    todo: list[At] = []

    def reach(output: Element, universe: Element | None) -> At:
        if (output, universe) not in reached:
            reached[output, universe] = None
            todo.append((output, universe))
        return output, universe

    def follow(entry: Resolution, universe: Element | None) -> At | None:
        """What an entry of `inputs`, or evidence, reads: None for an input or nothing."""
        output = entry.element
        if output is None or output.kind != "output":
            return None
        at = read_in(entry, universe, pinned, per_universe)
        if output in per_universe and at is None:  # a pin that names no universe (case 5)
            return None
        reads[entry, at] = None
        return reach(output, at)

    outputs = [Element(driver, "output", id_) for id_ in analysis.outputs]
    for output in (*outputs, *requested):  # one asked for, as the driver's own
        for universe in own if output in per_universe else [None]:
            roots.append(reach(output, universe))
    for entry in stack.resolutions:
        if entry.field == "artifact" and entry.file == driver:
            unpinned = entry.pin is None and entry.element in per_universe
            for universe in own if unpinned else [None]:
                cited = follow(entry, universe)
                if cited is not None:
                    roots.append(cited)
    while todo:
        output, universe = todo.pop(0)
        if output in cycles or (universe is not None and selections[universe] is None):
            continue
        for entry in written[output]:
            if entry.field == "decisions":
                reads[entry, universe] = None
            elif entry.field == "inputs":
                read = follow(entry, universe)
                if read is not None:
                    edges.setdefault((output, universe), []).append(read)

    status: dict[At, bool | None] = {}
    improved: list[At] = []

    def plan(key: At, found: bool | None) -> None:
        if found is False or (key in status and (status[key] is True or found is None)):
            return
        status[key] = found
        improved.append(key)

    for root in roots:
        plan(root, meaning.built(*root))
    while improved:
        key = improved.pop(0)
        for read in edges.get(key, ()):
            plan(read, _both(status[key], meaning.built(*read)))
    planned = {key: status[key] for key in reached if key in status}
    return Run(driver, MappingProxyType(reached), MappingProxyType(planned), tuple(reads))


@dataclass(frozen=True)
class Building:
    """What building the root builds (§16 *The universe being built*, §18)."""

    universes: Mapping[Element, Mapping[Identity, tuple[Chain, ...]]]
    """Each universe built, the root's first, then each other its run reads in, with the analyses
    built in it: its driver, the analysis whose universe it is, by the empty chain, then each its
    driver's universes drive, by the chains that reach it (`built`)."""
    planned: Mapping[At, Planned]
    """Each planned result, by its output and universe, in the order reached."""
    reads: tuple[tuple[Resolution, Element | None], ...]
    """Each address the root's run follows, with the universe it is read in (`Run.reads`)."""
    run: Run
    """The root's run."""


def building(stack: Stack, run: Run, chains: Mapping[Identity, tuple[Chain, ...]]) -> Building:
    """What building the root, `run`'s driver, builds (§16 *The universe being built*, §18), from
    the chains each analysis's universes drive (`driven`): its own universes, and each other
    universe its run reads in, each with the analyses built in it (`built`); and a result for
    each output `run` plans (True) where it is built once, or where its analysis is built in its
    universe. Any other output planned has no result: its planning is undetermined (design §4.13
    case 12)."""
    universes: dict[Element, Mapping[Identity, tuple[Chain, ...]]] = {}
    own = [
        Element(run.driver, "universe", id_)
        for id_, universe in stack.analysis(run.driver).universes.items()
        if not universe.is_import
    ]
    for each in (*own, *(at for _, at in run.reads if at is not None)):
        if each not in universes:
            universes[each] = built(chains[each.analysis], each.analysis)
    planned: dict[At, Planned] = {}
    for (output, universe), status in run.planned.items():
        # a result built once is its output's analysis's; none where its analysis isn't built
        named = ((),) if universe is None else universes[universe].get(output.analysis)
        if status is True and named is not None:
            planned[output, universe] = Planned(output, universe, named)
    return Building(MappingProxyType(universes), MappingProxyType(planned), run.reads, run)
