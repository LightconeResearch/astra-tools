"""What each universe selects, what each switch takes, what is built, reached, planned and used
in it, and what is driven (§12, §13, §16, §18; Elements, Results; design §2).

Pure functions of a Stack, each of which `rules.Context` computes once:

- `selections`: every universe's effective selection (§12; design §4.13 case 7);
- `written`: the addresses each decision, output and switch writes;
- `imports` and `pins`: the universe each import and each pin names (§16 *Pins and imported
  universes*);
- `per_universe`: the outputs built per universe, every other output but a switch being built
  once (§13; Elements *built per universe*);
- `depends` and `cycles`: what each output and switch reads directly, through `inputs` and
  `cases`, and those that read themselves (§10; Rules `OUTPUT_CYCLE`);
- `Meaning`: the case each switch takes in each universe (Elements *takes*), whether each element
  is built there, which never turns on driving (Results *built*), why one isn't (`Cause`), and
  what a reference reads through the case each switch takes (`Through`);
- `run`: with one analysis driving, what it reaches from its planning roots, built or not, the
  universe each address it follows is read in, the pins it follows into other analyses'
  universes, what it plans, and the decisions each universe uses, may use (where a switch is
  undetermined, design §4.13 case 6) and uses on some branch (Results *plans*, *reaches*, *uses*,
  *uses on some branch*);
- `driven` and `unsettled`: the chains of declarations each analysis's universes drive, given the
  decisions they use (§16 *Driving*; Elements), and those whose driving is undetermined; `built`,
  the analyses built in its universes, whose decisions they set;
- `building`: of the root's run, the universes built, and the planned results whose analysis is
  built in their universe, each with its names (§16 *The universe being built*, §18); `places`,
  where each name of a planned result puts its record and its bytes (§18 *Where records and bytes
  go*).

A universe is named by its analysis and its id (§16 *The universe being built*): an `Element` of
kind `universe`, so imports of one universe, under any ids, name one Element.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from astra import model
from astra.stack import Declaration, Element, Identity, Kind, Resolution, Stack

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


def own_universes(stack: Stack, analysis: Identity) -> tuple[Element, ...]:
    """`analysis`'s universes, in its file's order, without its imports, which select nothing."""
    return tuple(
        Element(analysis, "universe", id_)
        for id_, universe in stack.analysis(analysis).universes.items()
        if not universe.is_import
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
    """The addresses each decision, output and switch of the stack's valid files writes, () for
    none: an output's `inputs` and `decisions`; a switch's `switch` and cases (Elements
    *switch*); a decision's options' constraints."""
    found: dict[Element, list[Resolution]] = {}
    for member, analysis in stack.determined():
        for id_ in analysis.decisions:
            found[Element(member.identity, "decision", id_)] = []
        for id_, output in analysis.outputs.items():
            kind: Kind = "switch" if output.is_switch else "output"
            found[Element(member.identity, kind, id_)] = []
    for resolution in stack.resolutions:
        owner = resolution.owner
        if owner is not None and owner.kind in ("output", "switch", "decision"):
            found[owner].append(resolution)
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


Used = Mapping[Identity, frozenset[Element]]
"""For each analysis driving, the decisions some universe of its own uses (Results *uses*)."""


def driven(
    stack: Stack, used: Used, maybe: Used | None = None
) -> Mapping[Identity, tuple[Chain, ...]]:
    """The chains of declarations from each analysis's file that its universes drive (§16
    *Which declarations are driven*; Elements), each driven on its own:

    - each chain a key goes through, but for a key that loops (design §4.13 case 10). Every key
      of an effective selection is one that a universe sets itself, and every key a universe
      sets is in its effective selection or counts in its place (case 7): so the keys that
      drive are those of the universes' own `decisions`;
    - and a driven chain, the empty one of the analysis's own file included, followed by a
      declaration, leading back to no analysis already on it, of an analysis with no decisions,
      or none that a universe of the driving analysis uses (`used`) or may use (`maybe`, where
      that is undetermined, design §4.13 case 6: see `unsettled`).

    An undetermined analysis's declarations aren't known, so none are driven (design §4.13 case 4).
    """
    found: dict[Identity, tuple[Chain, ...]] = {}
    for member, _ in stack.determined():
        identity = member.identity
        counted = used.get(identity, frozenset()) | (maybe or {}).get(identity, frozenset())
        found[identity] = tuple(_chains(stack, identity, counted))
    return MappingProxyType(found)


def _chains(stack: Stack, driver: Identity, counted: frozenset[Element]) -> dict[Chain, None]:
    """The chains `driver`'s universes drive, extending through an analysis none of whose
    decisions is in `counted`."""
    chains: dict[Chain, None] = {}
    for key in stack.resolutions:
        if key.field == "selection" and key.file == driver and looping(key) is None:
            # through the declarations it resolves, whatever its last id names (design
            # §4.13 case 5)
            for end in range(1, len(key.chain) + 1):
                chains[key.chain[:end]] = None
    todo: list[Chain] = [(), *chains]
    while todo:
        chain = todo.pop(0)
        for declaration in _extending(stack, driver, chain):
            longer = (*chain, declaration)
            if not _uses_any(stack, declaration, counted) and longer not in chains:
                chains[longer] = None
                todo.append(longer)
    return chains


def _extending(stack: Stack, driver: Identity, chain: Chain) -> Iterable[Declaration]:
    """The declarations that may extend `chain`: those of the analysis it ends at that reach an
    analysis, and lead back to none already on it."""
    folder = chain[-1].reached if chain else driver
    if folder is None or (chain and chain[-1].outcome != "reached"):
        return ()
    on_chain = (driver, *(declaration.reached for declaration in chain))
    return [
        declaration
        for declaration in stack.analyses[folder].declarations.values()
        if declaration.outcome == "reached" and declaration.reached not in on_chain
    ]


def _uses_any(stack: Stack, declaration: Declaration, decisions: frozenset[Element]) -> bool:
    """Whether one of `decisions` is a decision of the analysis `declaration` reaches, or may be:
    an undetermined one's aren't known."""
    reached = declaration.reached
    analysis = None if reached is None else stack.analyses[reached].analysis
    if reached is None or analysis is None:
        return True
    return any(Element(reached, "decision", id_) in decisions for id_ in analysis.decisions)


def unsettled(stack: Stack, used: Used, maybe: Used) -> Mapping[Identity, frozenset[Chain]]:
    """For each analysis driving, the chains whose driving is undetermined (design §4.13 case 6,
    *undetermined driving*): a driven chain followed by a declaration, leading back to nothing on
    it, of an analysis that no key drives, none of whose decisions a universe of the driving
    analysis uses, and one of whose decisions one may use. They aren't driven (`driven`)."""
    chains = driven(stack, used, maybe)
    found: dict[Identity, frozenset[Chain]] = {}
    for member, _ in stack.determined():
        identity = member.identity
        definite = used.get(identity, frozenset())
        possible = maybe.get(identity, frozenset())
        found[identity] = frozenset(
            (*chain, declaration)
            for chain in ((), *chains[identity])
            for declaration in _extending(stack, identity, chain)
            if (*chain, declaration) not in chains[identity]
            and not _uses_any(stack, declaration, definite)
            and _uses_any(stack, declaration, possible)
        )
    return MappingProxyType(found)


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
    """The outputs built per universe (§13 *Built per universe or built once*; Elements *built
    per universe*): each output other than a switch that lists `decisions`, or has an unpinned
    entry of `inputs` naming a switch or an output built per universe, through any declaration.
    Every other output is built once; a switch is neither. An entry that names nothing names no
    output (design §4.13 case 5)."""
    found = {
        Element(member.identity, "output", id_)
        for member, analysis in stack.determined()
        for id_, output in analysis.outputs.items()
        if not output.is_switch and output.decisions
    }
    reads = [entry for entry in stack.resolutions if entry.field == "inputs" and entry.pin is None]
    grown = True
    while grown:
        grown = False
        for entry in reads:
            element = entry.element
            if entry.owner in found or element is None:
                continue
            if element in found or element.kind == "switch":
                assert entry.owner is not None  # the output whose `inputs` holds it
                found.add(entry.owner)
                grown = True
    return frozenset(found)


Depends = Mapping[Element, tuple[tuple[Element, Resolution], ...]]
"""What each output reads through `Output.inputs`, and each switch through its `cases`: each output
or switch an entry or a case names, with the entry or the case."""


def depends(stack: Stack) -> Depends:
    """What each output and switch depends on directly (§10; Rules `OUTPUT_CYCLE`): each output
    or switch that an entry of its `inputs`, or one of its cases, names, pinned or not, taken or
    not, through any declaration, known by its analysis's identity. An address that names
    nothing names no output (design §4.13 cases 4 and 5)."""
    found: dict[Element, list[tuple[Element, Resolution]]] = {}
    for entry in stack.resolutions:
        element = entry.element
        if entry.field in ("inputs", "case") and element is not None:
            if element.kind in ("output", "switch"):
                assert entry.owner is not None  # the output or switch that writes it
                found.setdefault(entry.owner, []).append((element, entry))
    return MappingProxyType({owner: tuple(entries) for owner, entries in found.items()})


def cycles(depends: Depends) -> frozenset[Element]:
    """The outputs and switches that depend on themselves, directly or through others (§10)."""
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
    assert format_ is not None  # a result's output isn't a switch
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
    """The universe in which an entry of `inputs`, a case, or evidence, read from `universe` or
    once, reads what it names (§13 *Pins*; Elements *takes*): for a switch, or an output built per
    universe, the one its pin names (`pins`), or else `universe`; None for an input or an output
    built once, whose one result is read pinned or not, and for a pin that names nothing."""
    element = entry.element
    if element is None or (element.kind != "switch" and element not in per_universe):
        return None
    return universe if entry.pin is None else pinned[entry]


At = tuple[Element, Element | None]
"""An element and the universe it is in, None for an output built once."""


@dataclass(frozen=True)
class Taken:
    """What a switch takes in a universe (Elements *takes*): the option its decision selects
    there, and the case keyed by it, None where it has none."""

    option: str
    case: Resolution | None


@dataclass(frozen=True)
class Step:
    """A switch read on the way through a reference: in the universe it is read in, the option
    its decision selects there and the case it takes."""

    switch: Element
    universe: Element
    option: str
    case: Resolution


@dataclass(frozen=True)
class Through:
    """What a reference reads, through the case each switch takes (Elements *takes*): an input,
    or an output other than a switch, in the universe it is read in."""

    entry: Resolution  # an entry of `inputs`, a case or an `artifact`, as written
    target: Element  # of kind `input` or `output`
    universe: Element | None  # where `target` is read; None for an input or an output built once
    steps: tuple[Step, ...]  # each switch on the way, in order

    @property
    def chain(self) -> Chain:
        """The declarations from the entry's file to the target's analysis: the entry's, then
        each case's."""
        return (*self.entry.chain, *(d for step in self.steps for d in step.case.chain))


@dataclass(frozen=True)
class Cause:
    """Why an element isn't built in a universe: a switch on the way has no case there for the
    option its decision selects (Elements *switch*)."""

    switch: Element
    universe: Element
    option: str


class Meaning:
    """What each switch takes in each universe (Elements *takes*), and whether each element is
    built there (Results *built*), each answer computed once. An input, and an output built
    once, always are; an output built per universe is where everything it reads without a pin
    is; a switch is where it takes a case, and what the case names is built where it reads it. A
    pinned entry of `inputs` never makes its reader not built (`PIN_NOT_BUILT` judges it). It
    never consults driving: an output can be built in a universe that doesn't build its
    analysis, and then has no result there (§16 *The universe being built*). One for each
    `rules.Context`."""

    def __init__(
        self,
        stack: Stack,
        written: Mapping[Element, tuple[Resolution, ...]],
        selections: Mapping[Element, Selection | None],
        pinned: Mapping[Resolution, Element | None],
        per_universe: frozenset[Element],
        cycles: frozenset[Element],
    ) -> None:
        self._stack = stack
        self._written = written
        self._selections = selections
        self._pinned = pinned
        self._per_universe = per_universe
        self._cycles = cycles
        self._taken: dict[At, Taken | None] = {}
        self._built: dict[At, bool | None] = {}

    def taken(self, switch: Element, universe: Element | None) -> Taken | None:
        """What `switch` takes in `universe`. None where that is undetermined (design §4.13
        case 6): the switch is on a cycle; the universe has no effective selection (case 7); its
        `switch` names nothing; its decision is unset there, or two of its options are selected;
        the option selected isn't one of its decision's, or is excluded; or that option has no
        case while a key of its `cases` names no option, which may be a misspelling of it."""
        key = (switch, universe)
        if key not in self._taken:
            self._taken[key] = self._take(switch, universe)
        return self._taken[key]

    def _take(self, switch: Element, universe: Element | None) -> Taken | None:
        selection = None if universe is None else self._selections.get(universe)
        if switch in self._cycles or selection is None:
            return None
        resolved = self._stack.switches[switch]
        decision = resolved.decision.element
        if decision is None:
            return None
        selected = selection.options(decision)
        if len(selected) != 1:
            return None
        (option,) = selected
        known = options(self._stack, decision)
        if option not in known or known[option].excluded is not None:
            return None
        case = resolved.cases.get(option)
        if case is None and any(key not in known for key in resolved.cases):
            return None
        return Taken(option, case)

    def built(self, element: Element, universe: Element | None) -> bool | None:
        """Whether `element`, an input, an output or a switch, is built in `universe` (None:
        once). None where that is undetermined: for an element on a cycle (design §4.13 case
        13); for an output built per universe, or a switch, in a universe with no effective
        selection (case 7); for a switch undetermined there (case 6); and for one that reads,
        without a pin, what names nothing (cases 4 and 5) or what is undetermined."""
        key = (element, universe)
        if key not in self._built:
            self._built[key] = None  # what reads itself is on a cycle, and undetermined
            self._built[key] = self._judged(element, universe)
        return self._built[key]

    def _judged(self, element: Element, universe: Element | None) -> bool | None:
        if element in self._cycles:
            return None
        if element.kind == "input" or (
            element.kind == "output" and element not in self._per_universe
        ):
            return True
        if universe is None or self._selections.get(universe) is None:
            return None
        if element.kind == "switch":
            taken = self.taken(element, universe)
            if taken is None or taken.case is None:
                return None if taken is None else False
            return self._reads(taken.case, universe)
        found: bool | None = True
        for entry in self._written[element]:
            if entry.field == "inputs" and entry.pin is None:
                found = _both(found, self._reads(entry, universe))
        return found

    def _reads(self, entry: Resolution, universe: Element) -> bool | None:
        """Whether what `entry`, an entry of `inputs` or a case, names is built where it reads
        it from `universe`."""
        element = entry.element
        if element is None or (entry.pin is not None and self._pinned[entry] is None):
            return None
        return self.built(element, read_in(entry, universe, self._pinned, self._per_universe))

    def cause(self, element: Element, universe: Element | None) -> Cause | None:
        """Why `element` isn't built in `universe`: the first switch, on the way through what it
        reads without a pin, that has no case there for the option its decision selects. None
        where it is built, or that is undetermined."""
        if self.built(element, universe) is not False:
            return None
        assert universe is not None  # only what is built per universe can be not built
        if element.kind == "switch":
            taken = self.taken(element, universe)
            assert taken is not None
            if taken.case is None:
                return Cause(element, universe, taken.option)
            return self._cause(taken.case, universe)
        for entry in self._written[element]:
            if entry.field == "inputs" and entry.pin is None:
                if self._reads(entry, universe) is False:
                    return self._cause(entry, universe)
        return None

    def _cause(self, entry: Resolution, universe: Element) -> Cause | None:
        assert entry.element is not None
        at = read_in(entry, universe, self._pinned, self._per_universe)
        return self.cause(entry.element, at)

    def through(self, entry: Resolution, universe: Element | None) -> Through | None:
        """What `entry`, an entry of `inputs`, a case or an `artifact`, reads from `universe`
        (None: once), through the case each switch on the way takes, in the universe each is read
        in (a pin sets it). None where anything on the way names nothing, a pin names no
        universe, or a switch is undetermined or takes nothing."""
        steps: list[Step] = []
        current, at = entry, universe
        while True:
            element = current.element
            if element is None or (current.pin is not None and self._pinned[current] is None):
                return None
            at = read_in(current, at, self._pinned, self._per_universe)
            if element.kind != "switch":
                if element in self._per_universe and at is None:
                    return None
                return Through(entry, element, at, tuple(steps))
            taken = self.taken(element, at)  # None on a cycle, so this ends
            if at is None or taken is None or taken.case is None:
                return None
            steps.append(Step(element, at, taken.option, taken.case))
            current = taken.case


def _both(one: bool | None, other: bool | None) -> bool | None:
    """Kleene's and, for what is built or planned: False over None, None over True."""
    if one is False or other is False:
        return False
    return None if one is None or other is None else True


@dataclass(frozen=True)
class PinRead:
    """A pin that a run follows into a universe of another analysis than its driver (Rules
    `PIN_NOT_BUILT`): the reference, the universe it names, and the decisions that what is
    reached through it uses there, an output those it lists and a switch the one it switches on,
    through what each reads without a pin and the case each switch takes."""

    entry: Resolution
    universe: Element
    uses: frozenset[Element]


@dataclass(frozen=True)
class Run:
    """What one analysis, driving, reaches, plans and uses (Results *plans*, *reaches*, *uses*,
    *uses on some branch*)."""

    driver: Identity
    reached: Mapping[At, None]
    """Each output and switch reached from the driver's planning roots, built there or not, by
    the universe it is reached in, None for an output built once, in the order reached."""
    planned: Mapping[At, bool | None]
    """Each output reached that is planned, in the order reached: True, or None where its
    planning is undetermined (design §4.13 cases 6 and 12)."""
    reads: tuple[tuple[Resolution, Element | None], ...]
    """Each address the reach follows, with the universe it is read in: each entry of a reached
    output's `decisions`, and a reached switch's `switch`, in its universe; and each entry of a
    reached output's `inputs`, the case each reached switch takes, and each of the driver's
    `artifact`s, that names an output or a switch, in the universe it reads it in (`read_in`),
    None for an output built once. A pin that names no universe reads nothing."""
    pins: tuple[PinRead, ...]
    """Each pin the reach follows into a universe of another analysis, in the order followed."""
    used: Mapping[Element, frozenset[Element]]
    """For each universe something is reached in, the decisions it uses: those that results
    planned there list, and those that switches reached there switch on (Results *uses*)."""
    maybe: Mapping[Element, frozenset[Element]]
    """For each universe, the decisions whose use there is undetermined, as it turns on a switch
    that is (design §4.13 case 6), and that it doesn't otherwise use."""
    branches: Mapping[Element, frozenset[Element]]
    """For each of the driver's universes, the decisions it uses on some branch, before a key's
    inheritors are counted (Results *uses on some branch*): those listed, or switched on, by what
    the driver reaches there with every case of every switch followed."""
    blind: frozenset[Identity]
    """The analyses whose universes' keys `UNUSED_DECISION` doesn't judge, since that reach met
    an address, or a pin, that names nothing (design §4.13 case 6)."""


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
    """What `driver` reaches, plans and uses (Results *plans*, *reaches*, *uses*), from what
    `meaning` says is taken and built, the addresses each element writes (`written`), the
    effective selections, the universe each pin names (`pins`), the outputs built per universe
    and the outputs and switches on a cycle; with the outputs `requested` as its own, to build
    them on request (`plan.plan`).

    Its planning roots are its own outputs other than switches that no case of its own names,
    its own switches that no entry of its own `inputs` and no case of its own names, and what
    its evidence cites: an output built once, and evidence citing one, once; other pinned
    evidence in the universe its pin names; any other in each of its universes. From an output
    reached, every entry of its `inputs` that names an output or a switch reaches it, in the
    universe it reads it in (`read_in`), whether either is built there or not; from a switch,
    only the case it takes. Nothing is followed from an element on a cycle (design §4.13 case
    13), nor in a universe with no effective selection (case 7). Reach never consults what is
    built, nor driving.

    A root is planned where it is built, and so is what a planned output or switch reads: each
    one's status, where it is reached through others, is the best of each reader's and its own
    (`_both`), True over None. Not built (False), it isn't planned."""
    own = own_universes(stack, driver)
    reached: dict[At, None] = {}
    reads: dict[tuple[Resolution, Element | None], None] = {}
    edges: dict[At, list[tuple[At, Resolution]]] = {}
    pinning: dict[tuple[Resolution, Element], None] = {}
    undetermined: list[At] = []
    roots: list[At] = []
    todo: list[At] = []

    def reach(element: Element, universe: Element | None) -> At:
        if (element, universe) not in reached:
            reached[element, universe] = None
            todo.append((element, universe))
        return element, universe

    def follow(entry: Resolution, universe: Element | None) -> At | None:
        """What an entry of `inputs`, a case or evidence reads: None for an input or nothing."""
        element = entry.element
        if element is None or element.kind == "input":
            return None
        if entry.field == "case" and entry.pin is not None and pinned[entry] is None:
            return None  # the switch is undetermined (design §4.13 case 6)
        at = read_in(entry, universe, pinned, per_universe)
        if (element.kind == "switch" or element in per_universe) and at is None:
            return None  # a pin that names no universe (case 5)
        reads[entry, at] = None
        if entry.pin is not None and at is not None and at.analysis != driver:
            pinning[entry, at] = None
        return reach(element, at)

    for element in _roots(stack, driver, requested):
        for universe in own if _each(element, per_universe) else [None]:
            roots.append(reach(element, universe))
    starts = list(roots)  # the roots but for what evidence cites, which `_branches` follows
    for entry in _cited(stack, driver):
        for universe in own if entry.pin is None and _each(entry.element, per_universe) else [None]:
            cited = follow(entry, universe)
            if cited is not None:
                roots.append(cited)
    while todo:
        element, universe = todo.pop(0)
        if element in cycles:
            undetermined.append((element, universe))
            continue
        if universe is not None and selections.get(universe) is None:
            continue
        if element.kind == "switch":
            reads[stack.switches[element].decision, universe] = None
            taken = meaning.taken(element, universe)
            if taken is None:
                undetermined.append((element, universe))
            elif taken.case is not None:
                read = follow(taken.case, universe)
                if read is not None:
                    edges.setdefault((element, universe), []).append((read, taken.case))
            continue
        for entry in written[element]:
            if entry.field == "decisions":
                reads[entry, universe] = None
            elif entry.field == "inputs":
                read = follow(entry, universe)
                if read is not None:
                    edges.setdefault((element, universe), []).append((read, entry))

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
        for read, _ in edges.get(key, ()):
            plan(read, _both(status[key], meaning.built(*read)))
    planned = {key: status[key] for key in reached if key in status and key[0].kind == "output"}

    used: dict[Element, set[Element]] = {}
    maybe: dict[Element, set[Element]] = {}
    for (element, universe), found in planned.items():
        if universe is not None:
            into = used if found is True else maybe
            into.setdefault(universe, set()).update(_listed(written, element))
    for element, universe in reached:
        if element.kind == "switch" and universe is not None and element not in cycles:
            used.setdefault(universe, set()).update(_switched_on(stack, element))
    for point in undetermined:
        beyond, _ = _branches(stack, written, pinned, per_universe, [point])
        for universe, decisions in beyond.items():
            if universe is not None:
                maybe.setdefault(universe, set()).update(decisions)

    pins_read = tuple(
        PinRead(entry, universe, _through_pin(stack, written, edges, (entry.element, universe)))
        for entry, universe in pinning
        if entry.element is not None
    )
    static, blind = _branches(
        stack, written, pinned, per_universe, starts, driver, _cited(stack, driver), own
    )
    return Run(
        driver,
        MappingProxyType(reached),
        MappingProxyType(planned),
        tuple(reads),
        pins_read,
        _frozen(used),
        _frozen({u: found - used.get(u, set()) for u, found in maybe.items()}),
        MappingProxyType({u: frozenset(static.get(u, ())) for u in own}),
        frozenset(blind),
    )


def _each(element: Element | None, per_universe: frozenset[Element]) -> bool:
    """Whether a root, or what evidence cites without a pin, is reached in each of the driver's
    universes, rather than once: a switch, or an output built per universe."""
    return element is not None and (element.kind == "switch" or element in per_universe)


def _roots(stack: Stack, driver: Identity, requested: tuple[Element, ...]) -> list[Element]:
    """`driver`'s own planning roots but for what its evidence cites (Results *plans*): its
    outputs other than switches that no case of its own names, its switches that no entry of its
    own `inputs` and no case of its own names, and the outputs `requested`."""
    named: set[Element] = set()
    read: set[Element] = set()
    for entry in stack.resolutions:
        if entry.file == driver and entry.element is not None:
            if entry.field == "case":
                named.add(entry.element)
            elif entry.field == "inputs":
                read.add(entry.element)
    found: list[Element] = []
    for id_, output in stack.analysis(driver).outputs.items():
        kind: Kind = "switch" if output.is_switch else "output"
        element = Element(driver, kind, id_)
        if element not in named and (kind == "output" or element not in read):
            found.append(element)
    return [*found, *requested]  # one asked for, as the driver's own


def _cited(stack: Stack, driver: Identity) -> list[Resolution]:
    """`driver`'s evidence's `artifact`s, in its file's order."""
    return [
        entry for entry in stack.resolutions if entry.field == "artifact" and entry.file == driver
    ]


def _listed(written: Mapping[Element, tuple[Resolution, ...]], output: Element) -> set[Element]:
    """The decisions an output lists, that its `decisions` name."""
    return {
        entry.element
        for entry in written[output]
        if entry.field == "decisions" and entry.element is not None
    }


def _switched_on(stack: Stack, switch: Element) -> set[Element]:
    """The decision a switch switches on, if its `switch` names one."""
    decision = stack.switches[switch].decision.element
    return set() if decision is None else {decision}


def _frozen(found: Mapping[Element, set[Element]]) -> Mapping[Element, frozenset[Element]]:
    return MappingProxyType({key: frozenset(value) for key, value in found.items()})


def _through_pin(
    stack: Stack,
    written: Mapping[Element, tuple[Resolution, ...]],
    edges: Mapping[At, list[tuple[At, Resolution]]],
    start: At,
) -> frozenset[Element]:
    """The decisions that what a run reaches from `start`, through what each reads without a pin
    and the case each switch takes, uses: an output those it lists, a switch the one it switches
    on (Rules `PIN_NOT_BUILT`)."""
    found: set[Element] = set()
    seen: set[At] = set()
    todo = [start]
    while todo:
        key = todo.pop()
        if key in seen:
            continue
        seen.add(key)
        element = key[0]
        found |= _switched_on(stack, element) if element.kind == "switch" else set()
        found |= _listed(written, element) if element.kind == "output" else set()
        todo.extend(read for read, entry in edges.get(key, ()) if entry.pin is None)
    return frozenset(found)


def _branches(
    stack: Stack,
    written: Mapping[Element, tuple[Resolution, ...]],
    pinned: Mapping[Resolution, Element | None],
    per_universe: frozenset[Element],
    starts: list[At],
    driver: Identity | None = None,
    cited: list[Resolution] | None = None,
    own: tuple[Element, ...] = (),
) -> tuple[dict[Element | None, set[Element]], set[Identity]]:
    """What is reached from `starts`, and from `cited` evidence, with every case of every switch
    followed, a case on an excluded option or keyed by no option too, whatever is taken or
    built, and through cycles (Results *uses on some branch*): for each universe, the decisions
    listed or switched on by what is reached there, a pinned read counting for its pin's
    universe. And, for `driver`, the analyses whose keys `UNUSED_DECISION` can't judge: `driver`
    where this meets an address that names nothing, and, where a pin names no universe, the
    analysis holding it and the one whose element it names (design §4.13 case 6)."""
    found: dict[Element | None, set[Element]] = {}
    blind: set[Identity] = set()
    seen: set[At] = set()
    todo: list[At] = []

    def nothing() -> None:
        if driver is not None:
            blind.add(driver)

    def follow(entry: Resolution, universe: Element | None) -> None:
        element = entry.element
        if element is None:
            nothing()
            return
        if entry.pin is not None and pinned[entry] is None:
            if driver is not None:
                blind.update((driver, entry.file, element.analysis))
            return
        if element.kind == "input":
            return
        at = read_in(entry, universe, pinned, per_universe)
        if (element.kind == "switch" or element in per_universe) and at is None:
            return
        todo.append((element, at))

    todo.extend(starts)
    for entry in cited or ():
        unpinned = entry.pin is None and _each(entry.element, per_universe)
        for universe in own if unpinned else [None]:
            follow(entry, universe)
    while todo:
        key = todo.pop()
        if key in seen:
            continue
        seen.add(key)
        element, universe = key
        if element.kind == "switch":
            resolved = stack.switches[element]
            if resolved.decision.element is None:
                nothing()
            found.setdefault(universe, set()).update(_switched_on(stack, element))
            for case in resolved.cases.values():
                follow(case, universe)
            continue
        for entry in written[element]:
            if entry.field == "decisions":
                if entry.element is None:
                    nothing()
                else:
                    found.setdefault(universe, set()).add(entry.element)
            elif entry.field == "inputs":
                follow(entry, universe)
    return found, blind


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
    own = own_universes(stack, run.driver)
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
