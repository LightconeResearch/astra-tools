"""Mechanical rendering of the ASTRA LinkML schema into agent-friendly text.

Pure transformation: every string emitted here comes from the schema via
``SchemaView``. No hand-authored prose about the data model lives in this file.
"""

from __future__ import annotations

import os
from functools import lru_cache

from linkml_runtime.utils.schemaview import SchemaView

from astra.datamodel import SCHEMA_DIRECTORY

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
    return head + "." if sep else flat


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
    sv = _view()
    known = set(sv.all_classes()) | set(sv.all_enums())
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

def _render_field_table(name: str) -> list[str]:
    sv = _view()
    known = set(sv.all_classes()) | set(sv.all_enums())
    rows = []
    for s in sv.class_induced_slots(name):
        flags = []
        if s.multivalued:
            flags.append("multivalued")
        if s.inlined or s.inlined_as_list:
            flags.append("inlined")
        rng = f"-> astra spec {s.range.lower()}" if s.range in known else (s.range or "string")
        rows.append(
            {
                "name": s.name,
                "req": "required" if s.required else "optional",
                "range": rng,
                "flags": " ".join(flags),
                "pattern": s.pattern or "",
                "desc": _first_sentence(s.description),
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
            out.append(f"      {r['desc']}")
        if r["pattern"]:
            out.append(f"      pattern: {r['pattern']}")
    return out


def _render_rules(name: str) -> list[str]:
    cls = _view().get_class(name)
    rules = [r for r in (cls.rules or []) if r.title]
    if not rules:
        return []

    # Collapse parallel rules that share a title stem (everything but the last
    # underscore-delimited token), e.g. from_alias_forbids_{label,options,...}.
    groups: dict[str, list] = {}
    order: list[str] = []
    for r in rules:
        stem, _, _ = r.title.rpartition("_")
        stem = stem or r.title
        if stem not in groups:
            order.append(stem)
        groups.setdefault(stem, []).append(r)

    out = ["Rules:"]
    for stem in order:
        members = groups[stem]
        if len(members) > 1:
            suffixes = ", ".join(m.title.rpartition("_")[2] for m in members)
            out.append(f"  {_humanize(stem)}: {suffixes}")
        else:
            r = members[0]
            out.append(f"  {_humanize(r.title)}")
            if r.description:
                out.append(f"      {_first_sentence(r.description)}")
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
    for schema in SCHEMA_ORDER:
        names = class_groups.get(schema, [])
        enums = enum_groups.get(schema, [])
        if not names and not enums:
            continue
        out.append(f"{schema.upper()}")
        width = max((len(n) for n in names + enums), default=0)
        for n in names:
            out.append(f"  {n:<{width}}  {_first_sentence(sv.get_class(n).description)}")
        for n in enums:
            out.append(f"  {n:<{width}}  (enum) {_first_sentence(sv.get_enum(n).description)}")
        out.append("")
    out.append("astra spec <term> for detail; astra spec --full dumps the entire "
               "reference (very long).")
    return "\n".join(out)


def render_full() -> str:
    """Every entry concatenated: summary, then each term in schema order."""
    parts = [render_summary(), ""]
    class_groups = _classes_by_schema()
    enum_groups = _enums_by_schema()
    sep = "\n" + "=" * 74 + "\n\n"
    for schema in SCHEMA_ORDER:
        for name in class_groups.get(schema, []) + enum_groups.get(schema, []):
            parts.append(render_term(name).rstrip())
    return sep.join(parts) + "\n"


def list_terms() -> list[str]:
    return sorted(t[0] for t in _terms().values())
