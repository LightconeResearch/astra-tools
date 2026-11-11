"""§16 Driving and consuming, the rules on selections: a universe's own `decisions` give each
decision one key (`DUPLICATE_ELEMENT`), and no key goes through a declaration that leads back
(`LOOPING_KEY`); every universe sets every decision it uses, of its analysis and of each analysis
its analysis's universes drive (`MISSING_DECISION`); and every pin names a universe
(`UNKNOWN_PIN_UNIVERSE`).

Every universe of every analysis of the stack is checked, a driven analysis's own included
(§16 *What a validator checks*), with its own analysis driving (Results *uses*). A universe with
no effective selection is checked by the first two on its own `decisions`, and not by
`MISSING_DECISION` (design §4.13 case 7), which isn't checked either for a decision of an
undetermined analysis (case 4), for one whose use is undetermined (case 6), nor through a chain
whose driving is (case 6, *undetermined driving*). A key or a reference that names nothing is
checked by none (case 5), but for `LOOPING_KEY`, judged on its declarations as far as they
resolve (case 10).

§16's rules on the universe being built: what something reached reads of another analysis's,
an output built per universe or a switch, and the decisions it uses, an output those it lists
and a switch the one it switches on, belong to an analysis built where it is read
(`NOT_BUILT_IN_UNIVERSE`); and in the file of the analysis whose universe it is, the file's
universes drive the address's chain of declarations (`UNDRIVEN_DECLARATION`); and no planned
result has two names (`RESULT_IN_TWO_PLACES`, §18). The first two hold over what the root reaches
(`universes.run`), in each universe it reaches something in, whether that is, or its analysis
is, built there or not, through the case each switch takes, and at a switch's own `switch` even
where it is undetermined; but not in a universe with no effective selection (design §4.13 case
7), nor through a chain whose driving is undetermined (case 6). A switch read is judged at the
address that reads it, whatever case it takes, and the case it takes at the case, in the
switch's file. Constraints use nothing. The last holds over the root's planned results
(`universes.building`).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from astra import model
from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.stack import Element, Identity, Resolution
from astra.universes import Chain, Selection, built, looping, own_keys, unlooped

CODES = frozenset(
    {
        "DUPLICATE_ELEMENT",
        "LOOPING_KEY",
        "MISSING_DECISION",
        "UNKNOWN_PIN_UNIVERSE",
        "NOT_BUILT_IN_UNIVERSE",
        "UNDRIVEN_DECLARATION",
        "RESULT_IN_TWO_PLACES",
    }
)


def check(context: Context) -> Iterator[Diagnostic]:
    for member, analysis in context.stack.determined():
        building = built(context.driven[member.identity], member.identity)
        for id_, universe in analysis.universes.items():
            if universe.is_import:
                continue
            element = Element(member.identity, "universe", id_)
            own = own_keys(context.stack, element)
            selection = context.selections[element]
            yield from _looping(context, own)
            yield from _duplicates(context, own, () if selection is None else selection.inherited)
            if selection is not None:
                yield from _missing(context, selection, universe, building)
    yield from _pins(context)
    uses = _uses(context)
    yield from _not_built(context, uses)
    yield from _undriven(context, uses)
    yield from _two_places(context)


def _looping(context: Context, own: tuple[Resolution, ...]) -> Iterator[Diagnostic]:
    for key in own:
        found = looping(key)
        if found is not None:
            index, back = found
            declaration = key.chain[index]
            named = ".".join(earlier.id for earlier in key.chain[:back])
            to = f"`{named}`" if named else "this analysis"
            message = (
                f"`{key.key}` goes through `{declaration.id}`, which leads back to {to}, already "
                f"on its chain: key the decision as `{unlooped(key)}`"
            )
            location = context.at(key.file, key.pointer, key.key)
            yield context.diagnostic("LOOPING_KEY", message, location)


def _duplicates(
    context: Context, own: tuple[Resolution, ...], inherited: tuple[Resolution, ...]
) -> Iterator[Diagnostic]:
    """Each own key that spells a decision the universe inherits under another key, or that an
    earlier key of its own spells: the inherited keys, or else the first own one, stand."""
    inherited_keys = {entry.key for entry in inherited}
    standing: dict[Element, Resolution] = {}
    for entry in reversed(inherited):
        if entry.element is not None:
            standing[entry.element] = entry
    for key in own:
        if key.element is None:
            continue
        other = standing.setdefault(key.element, key)
        if other is key or key.key in inherited_keys:
            continue
        if other.key in inherited_keys:
            message = (
                f"`{key.key}` spells the decision this universe inherits as `{other.key}`: set "
                f"it under `{other.key}`, and remove `{key.key}`"
            )
        else:
            message = (
                f"`{key.key}` and `{other.key}` spell one decision, which a universe sets under "
                "one key: remove one or the other"
            )
        location = context.at(key.file, key.pointer, key.key)
        related = context.at(other.file, other.pointer, other.key)
        yield context.diagnostic("DUPLICATE_ELEMENT", message, location, [related])


def _missing(
    context: Context,
    selection: Selection,
    universe: model.Universe,
    building: Mapping[Identity, tuple[Chain, ...]],
) -> Iterator[Diagnostic]:
    """Each decision the universe uses that its effective selection leaves unset, of the
    universe's analysis and of each analysis its analysis's universes drive (§16 *What a universe
    sets*; Results *uses*), spelled through the first chain that reaches it."""
    name = selection.universe
    used = context.used(name)
    pointer = ("universes", name.id, "decisions") if universe.decisions else ("universes", name.id)
    location = context.at(name.analysis, pointer)  # design §3
    for identity, chains in building.items():
        chain = chains[0]
        for id_ in context.stack.analysis(identity).decisions:
            decision = Element(identity, "decision", id_)
            if decision not in used or selection.options(decision):
                continue
            spelled = ".".join((*(declaration.id for declaration in chain), id_))
            message = f"`{name.id}` selects nothing for `{spelled}`, which it uses"
            if chain:
                through = ".".join(declaration.id for declaration in chain)
                message += (
                    f": this analysis's universes drive `{through}`, so each of them sets the "
                    "decisions of it that it uses"
                )
            yield context.diagnostic("MISSING_DECISION", message, location)


def _pins(context: Context) -> Iterator[Diagnostic]:
    """Each pin whose file has no entry with its id, where the analysis whose element its
    reference names has no universe with that id either (§16 *Pins and imported universes*)."""
    stack = context.stack
    for resolution in stack.resolutions:
        pin, element = resolution.pin, resolution.element
        if pin is None or element is None:  # design §4.13 case 5
            continue
        if pin in stack.analysis(resolution.file).universes or context.pins[resolution] is not None:
            continue
        detail = f"this file's `universes` has no entry `{pin}`"
        if element.analysis != resolution.file:
            through = ".".join(resolution.address.declarations)
            imported = pin in stack.analysis(element.analysis).universes
            detail += (
                f", and `{pin}` is an import in `{through}`'s file, not one of its universes"
                if imported
                else f", nor has `{through}` a universe `{pin}`"
            )
        message = f"the pin `#{pin}` of `{resolution.written}` names no universe: {detail}"
        location = context.at(resolution.file, resolution.pointer)
        yield context.diagnostic("UNKNOWN_PIN_UNIVERSE", message, location)


# --- the universe being built ---

Uses = Mapping[Resolution, tuple[Element, ...]]
"""Each address that §16's rules on the universe being built hold, with the universes it is read
in, in the order reached."""


def _uses(context: Context) -> Uses:
    """Where the rules on the universe being built apply (`NOT_BUILT_IN_UNIVERSE` and
    `UNDRIVEN_DECLARATION`, §16 *The rules*), over what the root reaches, built or not
    (`universes.run`), each address in the universe it is read in:

    - each decision a reached output lists, and the decision a reached switch switches on, even
      where the switch is undetermined;
    - what a reached output's `inputs` entry, the case a reached switch takes, or the root's
      evidence reads, pinned or not, that is an output built per universe or a switch, whatever
      case that switch takes.

    Not in a universe with no effective selection (design §4.13 case 7), not for an address that
    names nothing (case 5), not for one that names an output or a switch on a cycle (case 13),
    not through a chain whose driving is undetermined (case 6), and not for one that names an
    element of its own file's analysis, which uses nothing of another (§15)."""
    found: dict[Resolution, dict[Element, None]] = {}
    per_universe = context.per_universe
    for entry, universe in context.building.reads:
        element = entry.element
        if universe is None or element is None or element.analysis == entry.file:
            continue
        if context.selections.get(universe) is None or context.on_cycle(element):
            continue
        if element.analysis in context.unsettled_in(universe):
            continue
        if entry.file == universe.analysis and context.unsettled_through(entry):
            continue
        read = element.kind == "switch" or element in per_universe
        if entry.field in ("decisions", "switch") or read:
            found.setdefault(entry, {})[universe] = None
    return {entry: tuple(universes) for entry, universes in found.items()}


def _used(entry: Resolution) -> str:
    """How an address uses its element, as a message says it."""
    if entry.field == "decisions":
        return "lists"
    if entry.field == "switch":
        return "switches on"
    return "reads" if entry.pin is None else "pins"


def _kind(element: Element) -> str:
    return {"output": "an output", "switch": "a switch"}.get(element.kind, "a decision")


def _not_built(context: Context, uses: Uses) -> Iterator[Diagnostic]:
    """Each use whose element's analysis isn't built in a universe built that holds it:
    `NOT_BUILT_IN_UNIVERSE` (§16 *The universe being built*)."""
    for entry, universes in uses.items():
        element = entry.element
        assert element is not None
        missing = [u for u in universes if element.analysis not in context.building.universes[u]]
        if not missing:
            continue
        where = "to" if entry.pin is not None else "in"
        message = (
            f"`{entry.written}` {_used(entry)} {_kind(element)} of `{element.analysis}` {where} "
            f"{context.named(missing, entry.file)}, where that analysis isn't built: no "
            "declaration those universes drive reaches it. Drive one from them"
        )
        if element.kind != "decision":
            message += ", or pin one of its own universes"
        location = context.at(entry.file, entry.pointer)
        yield context.diagnostic("NOT_BUILT_IN_UNIVERSE", message, location)


def _undriven(context: Context, uses: Uses) -> Iterator[Diagnostic]:
    """Each use of another analysis's element, in the file of the analysis whose universe holds
    it, whose chain of declarations that file's universes don't drive: `UNDRIVEN_DECLARATION`
    (§16 *The universe being built*). An address through a declaration back to its file's own
    analysis names one of its own elements, and consumes nothing (§15)."""
    for entry, universes in uses.items():
        element = entry.element
        assert element is not None
        theirs = [u for u in universes if u.analysis == entry.file]
        if not theirs or element.analysis == entry.file:
            continue
        driven = context.driven[entry.file]
        if entry.chain in driven:
            continue
        end = next(end for end in range(1, len(entry.chain) + 1) if entry.chain[:end] not in driven)
        first = ".".join(declaration.id for declaration in entry.chain[:end])
        where = "to" if entry.pin is not None else "in"
        message = (
            f"`{entry.written}` {_used(entry)} {_kind(element)} {where} "
            f"{context.named(theirs, entry.file)} through `{first}`, which this file's "
            "universes don't drive: set a decision through it in their `decisions`, or reach "
            "it through a declaration they drive"
        )
        location = context.at(entry.file, entry.pointer)
        yield context.diagnostic("UNDRIVEN_DECLARATION", message, location)


def _two_places(context: Context) -> Iterator[Diagnostic]:
    """For each pair of a planned result's names, a warning at the first declaration of each of
    their chains that the other doesn't go through, in the file that holds it, with the other as
    a related place (§18 *Which analysis a result belongs to, and its name*): one for all the
    universes the pair names one result in. Not for an output on a cycle (design §4.13 case 13)."""
    pairs: dict[tuple[str, Chain, str, Chain, str], list[Element]] = {}
    for planned in context.building.planned.values():
        if planned.universe is not None and not context.on_cycle(planned.output):  # case 13
            named = list(zip(planned.chains, planned.names, strict=True))
            for index, (chain, name) in enumerate(named):
                for other, other_name in named[index + 1 :]:
                    key = (planned.output.id, chain, name, other, other_name)
                    pairs.setdefault(key, []).append(planned.universe)
    for (output, one, one_name, two, two_name), universes in pairs.items():
        names = f"`{one_name}` and `{two_name}`"
        firsts = [
            next(d for d in chain if d not in other) for chain, other in ((one, two), (two, one))
        ]
        places = [context.at(first.owner, ("analyses", first.id)) for first in firsts]
        for first, place, related in zip(firsts, places, places[::-1], strict=True):
            message = (
                f"the result of `{output}` in {context.named(universes, first.owner)} has two "
                f"names, {names}, since those universes drive two chains of declarations to its "
                "analysis, through this one and through the related one: drive it through one "
                "chain only"
            )
            yield context.diagnostic("RESULT_IN_TWO_PLACES", message, place, [related])
