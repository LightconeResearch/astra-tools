"""Mechanical rendering of the ASTRA LinkML schema into agent-friendly text.

Pure transformation: every string emitted here comes from the schema via
``SchemaView``. No hand-authored prose about the data model lives in this file.
"""

from __future__ import annotations

import os
import shutil
import textwrap
from functools import lru_cache
from typing import Any

from astra.datamodel import SCHEMA_DIRECTORY
from linkml_runtime.utils.schemaview import SchemaView

# The three schema files map to the three conceptual layers ASTRA groups by.
# `from_schema` on each class carries the source schema URI; we key on its tail.
SCHEMA_ORDER = ["analysis", "universe", "insight"]


@lru_cache(maxsize=1)
def _view() -> SchemaView:
    # analysis.yaml imports insight + universe, so one load closes over all three.
    return SchemaView(os.path.join(SCHEMA_DIRECTORY, "analysis.yaml"))


def _schema_of(from_schema: str | None) -> str:
    return (from_schema or "").rstrip("/").rsplit("/", 1)[-1]


def _first_sentence(text: str | None) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    head, sep, _ = flat.partition(". ")
    return (head if sep else flat).rstrip(".") + "."


def _wrap_at(text: str, indent: int, hang: int = 0) -> list[str]:
    """Wrap text to the terminal width, indented `indent` spaces; continuation
    lines hang `hang` further so they read as part of the paragraph above."""
    cols = max(shutil.get_terminal_size(fallback=(100, 24)).columns, indent + hang + 20)
    return textwrap.wrap(
        text,
        width=cols,
        initial_indent=" " * indent,
        subsequent_indent=" " * (indent + hang),
    ) or [""]


def _hard_wrap_at(text: str, indent: int, hang: int = 0) -> list[str]:
    """Like ``_wrap_at`` but chunks unbreakable text (regexes) at the width limit."""
    cols = max(shutil.get_terminal_size(fallback=(100, 24)).columns, indent + hang + 20)
    pos, width = cols - indent, cols - indent - hang
    out = [f"{' ' * indent}{text[:pos]}"]
    while pos < len(text):
        out.append(f"{' ' * (indent + hang)}{text[pos : pos + width]}")
        pos += width
    return out


def _two_col(name: str, desc: str, width: int) -> list[str]:
    """One vocabulary-map row: name column, then desc wrapped within its own column."""
    lines = _wrap_at(desc, 2 + width + 2)
    return [f"  {name:<{width}}  {lines[0].lstrip()}".rstrip()] + lines[1:]


def _humanize(token: str) -> str:
    s = token.replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else s


# --------------------------------------------------------------------------
# Term registry
# --------------------------------------------------------------------------


def _terms() -> dict[str, tuple[str, str]]:
    """Map lowercased term -> (canonical name, kind) for every class and enum."""
    sv = _view()
    terms: dict[str, tuple[str, str]] = {}
    for name in sv.all_classes():
        terms[name.lower()] = (name, "class")
    for name in sv.all_enums():
        terms[name.lower()] = (name, "enum")
    return terms


def _classes_by_schema() -> dict[str, list[str]]:
    sv = _view()
    groups: dict[str, list[str]] = {s: [] for s in SCHEMA_ORDER}
    for name, cls in sv.all_classes().items():
        groups.setdefault(_schema_of(cls.from_schema), []).append(name)
    return groups


def _enums_by_schema() -> dict[str, list[str]]:
    sv = _view()
    groups: dict[str, list[str]] = {s: [] for s in SCHEMA_ORDER}
    for name, enm in sv.all_enums().items():
        groups.setdefault(_schema_of(enm.from_schema), []).append(name)
    return groups


def _schema_display_order(*group_dicts: dict[str, list[str]]) -> list[str]:
    """SCHEMA_ORDER first, then any other schema buckets (sorted).

    Guarantees every bucket is rendered: a schema file astra-spec grows beyond
    the three known layers still appears, appended after them, rather than being
    silently dropped from the summary and full dump.
    """
    extra = sorted({s for g in group_dicts for s in g} - set(SCHEMA_ORDER))
    return SCHEMA_ORDER + extra


# --------------------------------------------------------------------------
# Cross-reference graph
# --------------------------------------------------------------------------


def _used_by(target: str) -> list[str]:
    # Self-edges (a class holding a slot ranged at itself) are kept, not
    # dropped: Analysis contains sub-Analyses, and that recursion is a real
    # part of the graph. It is flagged at render time via `_term_ref`.
    sv = _view()
    users = [
        name
        for name, _ in sv.all_classes().items()
        if any(s.range == target for s in sv.class_induced_slots(name))
    ]
    return users


def _references(name: str) -> list[str]:
    # Enums are inlined into field rows, so only classes count as references.
    sv = _view()
    known = set(sv.all_classes())
    seen: list[str] = []
    for s in sv.class_induced_slots(name):
        if s.range in known and s.range not in seen:
            seen.append(s.range)
    return seen


def _term_link(name: str) -> str:
    return f"{name} (astra spec {name.lower()})"


def _term_ref(name: str, current: str) -> str:
    """Cross-reference link, marking an edge back to the current term."""
    return f"{name} (self-recursive)" if name == current else _term_link(name)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _enum_inline(name: str) -> tuple[str, str]:
    """(range text, description suffix) inlining an enum's values into a field row.

    Enums are rendered as facts about the fields that use them, not standalone
    concepts: the range column carries the literal values, and any per-value
    glosses fold into the field description.
    """
    values = _view().get_enum(name).permissible_values or {}
    rng = " | ".join(values)
    glosses = "; ".join(
        f"{v}: {_first_sentence(pv.description).rstrip('.')}"
        for v, pv in values.items()
        if pv.description
    )
    return rng, f" ({glosses})." if glosses else ""


def _render_field_table(name: str) -> list[str]:
    sv = _view()
    enums = set(sv.all_enums())
    rows = []
    for s in sv.class_induced_slots(name):
        flags = []
        if s.multivalued:
            flags.append("multivalued")
        if s.inlined or s.inlined_as_list:
            flags.append("inlined")
        desc_suffix = ""
        if s.range in enums:
            rng, desc_suffix = _enum_inline(s.range)
        elif s.range in sv.all_classes():
            rng = f"-> astra spec {s.range.lower()}"
        else:
            rng = s.range or sv.schema.default_range
        rows.append(
            {
                "name": s.name,
                "req": "required" if s.required else "optional",
                "range": rng,
                "flags": " ".join(flags),
                "pattern": s.pattern or "",
                "desc": (_first_sentence(s.description).rstrip(".") + desc_suffix)
                if desc_suffix
                else _first_sentence(s.description),
            }
        )
    if not rows:
        return []

    widths = {k: max(len(r[k]) for r in rows) for k in ("name", "req", "range", "flags")}
    widths = {k: max(v, len(h)) for (k, v), h in zip(widths.items(), ("field", "", "range", ""))}
    out = ["Fields:"]
    for r in rows:
        line = (
            f"  {r['name']:<{widths['name']}}  "
            f"{r['req']:<{widths['req']}}  "
            f"{r['range']:<{widths['range']}}"
        )
        if r["flags"]:
            line += f"  {r['flags']}"
        out.append(line.rstrip())
        if r["desc"]:
            out.extend(_wrap_at(r["desc"], 6, hang=2))
        if r["pattern"]:
            out.extend(_hard_wrap_at(f"pattern: {r['pattern']}", 6, hang=2))
    return out


def _forbidden_slot(rule: Any) -> str | None:
    """The single slot a forbid-rule marks absent, or ``None``.

    Read from the postcondition -- the real slot name, underscores intact --
    not the title, so multi-token names like ``ref_version`` survive.
    """
    conds = getattr(rule.postconditions, "slot_conditions", None) or {}
    if len(conds) != 1:
        return None
    ((slot, cond),) = conds.items()
    presence = getattr(cond, "value_presence", None)
    return slot if presence is not None and str(presence) == "ABSENT" else None


def _render_rules(name: str) -> list[str]:
    cls = _view().get_class(name)
    rules = [r for r in (cls.rules or []) if r.title]
    if not rules:
        return []

    # Collapse parallel forbid-rules -- those marking one slot absent under a
    # shared precondition, e.g. from_alias_forbids_{label,ref_version,...}. The
    # forbidden slot comes from the postcondition (so underscored names stay
    # intact); the group label is the title with that suffix stripped. Stripping
    # a whole shared prefix this way, rather than one trailing token, is what
    # keeps ref_version/use_outputs in their family instead of orphaning them.
    groups: dict[str, list[tuple[Any, str | None]]] = {}
    order: list[str] = []
    for r in rules:
        slot = _forbidden_slot(r)
        stem = r.title[: -(len(slot) + 1)] if slot and r.title.endswith("_" + slot) else r.title
        if stem not in groups:
            order.append(stem)
        groups.setdefault(stem, []).append((r, slot))

    out = ["Rules:"]
    for stem in order:
        members = groups[stem]
        forbids = [slot for _, slot in members if slot is not None]
        if len(members) > 1 and len(forbids) == len(members):
            out.append(f"  {_humanize(stem)}: {', '.join(forbids)}")
        else:
            for r, _ in members:
                out.append(f"  {_humanize(r.title)}")
                if r.description:
                    out.extend(_wrap_at(_first_sentence(r.description), 6, hang=2))
    return out


def _render_enum(name: str) -> str:
    enm = _view().get_enum(name)
    out = [f"# {name}  (enum)", ""]
    if enm.description:
        out.append(_first_sentence(enm.description))
        out.append("")
    out.append("Values:")
    for vname, v in (enm.permissible_values or {}).items():
        desc = _first_sentence(v.description) if v.description else ""
        out.append(f"  {vname}" + (f"  -- {desc}" if desc else ""))
    out.append("")
    used = _used_by(name)
    if used:
        out.append("Used by: " + ", ".join(_term_link(u) for u in used))
    return "\n".join(out).rstrip() + "\n"


def render_term(term: str) -> str:
    """Full rendered entry for a single class or enum. Returns '' if unknown."""
    hit = _terms().get(term.lower())
    if hit is None:
        return ""
    name, kind = hit
    if kind == "enum":
        return _render_enum(name)

    sv = _view()
    cls = sv.get_class(name)
    out = [f"# {name}" + ("  (tree root)" if cls.tree_root else ""), ""]
    if cls.description:
        # Verbatim: folded-scalar descriptions carry intentional grammar/example
        # blocks (indented lines survive YAML folding), so keep the line breaks.
        out.append("\n".join(line.rstrip() for line in cls.description.rstrip().splitlines()))
        out.append("")
    out.extend(_render_field_table(name))
    rules = _render_rules(name)
    if rules:
        out.append("")
        out.extend(rules)

    refs = _references(name)
    used = _used_by(name)
    if refs or used:
        out.append("")
    if refs:
        out.append("References: " + ", ".join(_term_ref(r, name) for r in refs))
    if used:
        out.append("Used by: " + ", ".join(_term_ref(u, name) for u in used))
    return "\n".join(out).rstrip() + "\n"


def render_summary() -> str:
    """One line per class/enum, grouped by schema, with a usage footer."""
    class_groups = _classes_by_schema()
    enum_groups = _enums_by_schema()
    sv = _view()

    out = ["ASTRA specification -- concept vocabulary", ""]
    for schema in _schema_display_order(class_groups, enum_groups):
        names = class_groups.get(schema, [])
        if not names:
            continue
        out.append(f"{schema.upper()}")
        width = max((len(n) for n in names), default=0)
        for n in names:
            out.extend(_two_col(n, _first_sentence(sv.get_class(n).description), width))
        out.append("")
    out.append(
        "astra spec <term> for detail; astra spec --full dumps the entire reference (very long)."
    )
    return "\n".join(out)


def render_full() -> str:
    """Every entry concatenated: summary, then each term in schema order."""
    # No empty-string sentinel here: joining `sep` against one would place two
    # `====` rules (with a blank line between) at the summary->first-entry seam,
    # inconsistent with every other single-rule boundary.
    parts = [render_summary()]
    class_groups = _classes_by_schema()
    enum_groups = _enums_by_schema()
    sep = "\n" + "=" * 74 + "\n\n"
    for schema in _schema_display_order(class_groups, enum_groups):
        for name in class_groups.get(schema, []):
            parts.append(render_term(name).rstrip())
    return sep.join(parts) + "\n"


def list_terms() -> list[str]:
    return sorted(t[0] for t in _terms().values())
