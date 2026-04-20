"""Narrative validation for ASTRA specifications.

Two checks layered on top of structural and semantic validation:

1. **Anchor resolution** — Markdown links inside ``narrative`` prose of
   the form ``[text](#target)`` must resolve to a declared element.
   Broken references are errors.

2. **Coverage** — each Analysis node's own decisions, findings, outputs,
   and sub-analyses should be mentioned somewhere in the narrative
   tree. Unmentioned elements emit warnings (not errors).

Anchor grammar is **tree-path-first**, matching the rest of ASTRA's
reference syntax (``sibling.output_id`` in ``from_ref``). Sub-analyses
are traversed before the category::

    #inputs.<id>
    #outputs.<id>
    #decisions.<id>
    #decisions.<id>.options.<id>
    #findings.<id>
    #prior_insights.<id>
    #analyses.<sub>
    #<sub>.<category>.<id>              (one level of nesting)
    #<sub>.<sub2>.<category>.<id>       (deeper nesting)

References are interpreted relative to the hosting analysis. Prefix
with ``../`` to escape to parent scope (may chain: ``../../``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astra.helpers import resolve_analysis_tree
from astra.validation.semantic import SemanticError

_HREF_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# Non-canonical "../" before "#" — the spec-canonical form puts the parent
# escape inside the fragment (e.g. (#../decisions.foo), not (../#decisions.foo)).
_PARENT_PATH_FORM_RE = re.compile(r"^(?:\.\./)+#")

_CATEGORIES = frozenset(
    {"inputs", "outputs", "decisions", "findings", "prior_insights", "analyses"}
)

# Categories whose elements are coverage-checked. Options, inputs, and
# prior_insights are intentionally excluded: options are typically
# numerous, inputs are often trivially "the data", and prior_insights
# exist to justify decisions rather than being independently noteworthy.
_COVERAGE_CATEGORIES = ("decisions", "findings", "outputs", "analyses")


@dataclass
class NarrativeWarning:
    """A non-breaking warning from narrative coverage checks."""

    code: str
    message: str
    path: str | None = None

    def __str__(self) -> str:
        if self.path:
            return f"[{self.code}] {self.path}: {self.message}"
        return f"[{self.code}] {self.message}"


@dataclass
class _ParsedAnchor:
    raw: str
    up_levels: int
    sub_path: tuple[str, ...]
    category: str
    element_id: str
    option_id: str | None


def _parse_anchor(raw: str) -> _ParsedAnchor | None:
    """Parse a raw anchor target (everything after ``#``) into segments.

    Returns None if the grammar doesn't match. The first segment that
    matches a reserved category name is treated as the category; any
    segments before it are sub-analysis names. This means sub-analyses
    named after reserved categories are ambiguous — avoid those names.
    """
    up = 0
    remaining = raw
    while remaining.startswith("../"):
        up += 1
        remaining = remaining[3:]

    if not remaining:
        return None

    segments = remaining.split(".")
    if any(not s for s in segments):
        return None

    cat_idx = -1
    for i, seg in enumerate(segments):
        if seg in _CATEGORIES:
            cat_idx = i
            break
    if cat_idx == -1:
        return None

    sub_path = tuple(segments[:cat_idx])
    category = segments[cat_idx]
    tail = segments[cat_idx + 1 :]
    if not tail:
        return None

    element_id = tail[0]
    option_id: str | None = None
    if category == "decisions":
        if len(tail) == 3 and tail[1] == "options":
            option_id = tail[2]
        elif len(tail) > 1:
            return None
    elif len(tail) > 1:
        return None

    return _ParsedAnchor(raw, up, sub_path, category, element_id, option_id)


def _get_node_at(root: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any] | None:
    """Walk ``root.analyses.<seg1>.analyses.<seg2>...`` and return the node."""
    current = root
    for seg in path:
        analyses = current.get("analyses") or {}
        if seg not in analyses:
            return None
        current = analyses[seg]
    return current


def _lookup_element(
    node: dict[str, Any], category: str, element_id: str, option_id: str | None
) -> bool:
    """Return True if ``element_id`` exists under ``category`` in ``node``."""
    if category == "inputs":
        return element_id in {inp.get("id") for inp in (node.get("inputs") or []) if inp.get("id")}
    if category == "outputs":
        return element_id in {out.get("id") for out in (node.get("outputs") or []) if out.get("id")}
    if category == "decisions":
        decisions = node.get("decisions") or {}
        if element_id not in decisions:
            return False
        if option_id is None:
            return True
        return option_id in (decisions[element_id].get("options") or {})
    if category == "findings":
        return element_id in (node.get("findings") or {})
    if category == "prior_insights":
        return element_id in (node.get("prior_insights") or {})
    if category == "analyses":
        return element_id in (node.get("analyses") or {})
    return False


def _resolve_anchor(
    anchor: _ParsedAnchor,
    hosting_path: tuple[str, ...],
    root: dict[str, Any],
) -> tuple[tuple[str, ...], str, str, str | None] | None:
    """Resolve an anchor to an absolute ``(target_path, category, id, option)``.

    Returns None if the anchor cannot be resolved (target node missing
    or element missing).
    """
    if anchor.up_levels > len(hosting_path):
        return None
    base = hosting_path[: len(hosting_path) - anchor.up_levels]
    target_path = base + anchor.sub_path
    target_node = _get_node_at(root, target_path)
    if target_node is None:
        return None
    if not _lookup_element(target_node, anchor.category, anchor.element_id, anchor.option_id):
        return None
    return (target_path, anchor.category, anchor.element_id, anchor.option_id)


def _extract_hrefs(narrative: Any) -> list[str]:
    """Extract all Markdown link hrefs from a narrative dict."""
    if not isinstance(narrative, dict):
        return []
    hrefs: list[str] = []
    for section_value in narrative.values():
        if isinstance(section_value, dict):
            text = section_value.get("content") or ""
        elif isinstance(section_value, str):
            text = section_value
        else:
            continue
        hrefs.extend(_HREF_RE.findall(text))
    return hrefs


def _node_path_str(path: tuple[str, ...]) -> str:
    """Render an absolute node path like ``analyses.foo.analyses.bar``."""
    return ".".join(f"analyses.{seg}" for seg in path)


def validate_narrative_anchors(
    data: dict[str, Any], base_path: Path | None = None
) -> list[SemanticError]:
    """Check that every narrative anchor reference resolves."""
    if base_path is not None:
        data = resolve_analysis_tree(data, base_path)
    errors: list[SemanticError] = []
    _walk_anchors(data, (), data, errors)
    return errors


def _walk_anchors(
    node: dict[str, Any],
    path: tuple[str, ...],
    root: dict[str, Any],
    errors: list[SemanticError],
) -> None:
    narrative = node.get("narrative")
    if narrative:
        base = _node_path_str(path)
        narrative_path = f"{base}.narrative" if base else "narrative"
        for href in _extract_hrefs(narrative):
            if _PARENT_PATH_FORM_RE.match(href):
                errors.append(
                    SemanticError(
                        "INVALID_NARRATIVE_ANCHOR",
                        f"Anchor '{href}' uses non-canonical parent escape; "
                        f"move '../' inside the fragment (e.g. '#../target' "
                        f"instead of '../#target')",
                        narrative_path,
                    )
                )
                continue
            if not href.startswith("#"):
                # External link (URL, relative file path, etc.) — not an ASTRA ref.
                continue
            raw = href[1:]
            if "." not in raw:
                # Plain Markdown heading anchor (e.g. [back to top](#abstract)),
                # not an ASTRA reference. Every valid ASTRA anchor has at least
                # `category.element_id`, so a dotless anchor cannot resolve.
                continue
            parsed = _parse_anchor(raw)
            if parsed is None:
                errors.append(
                    SemanticError(
                        "INVALID_NARRATIVE_ANCHOR",
                        f"Anchor '#{raw}' does not match the narrative anchor grammar",
                        narrative_path,
                    )
                )
                continue
            if _resolve_anchor(parsed, path, root) is None:
                errors.append(
                    SemanticError(
                        "BROKEN_NARRATIVE_ANCHOR",
                        f"Anchor '#{raw}' does not resolve to a declared element",
                        narrative_path,
                    )
                )
    for sub_id, sub_node in (node.get("analyses") or {}).items():
        _walk_anchors(sub_node, path + (sub_id,), root, errors)


def check_narrative_coverage(
    data: dict[str, Any], base_path: Path | None = None
) -> list[NarrativeWarning]:
    """Warn about decisions, findings, outputs, and sub-analyses not
    mentioned in any narrative across the analysis tree.

    A reference anywhere in the tree counts toward the target
    element's coverage — e.g. the root's narrative mentioning
    ``#child.decisions.foo`` satisfies coverage for that decision in
    the child. Mentioning a descendant also implicitly mentions each
    sub-analysis along the path.
    """
    if base_path is not None:
        data = resolve_analysis_tree(data, base_path)
    mentioned: set[tuple[tuple[str, ...], str, str]] = set()
    _collect_mentioned(data, (), data, mentioned)
    warnings: list[NarrativeWarning] = []
    _walk_coverage(data, (), mentioned, warnings)
    return warnings


def _collect_mentioned(
    node: dict[str, Any],
    path: tuple[str, ...],
    root: dict[str, Any],
    mentioned: set[tuple[tuple[str, ...], str, str]],
) -> None:
    narrative = node.get("narrative")
    if narrative:
        for href in _extract_hrefs(narrative):
            if not href.startswith("#"):
                continue
            raw = href[1:]
            if "." not in raw:
                continue
            parsed = _parse_anchor(raw)
            if parsed is None:
                continue
            resolved = _resolve_anchor(parsed, path, root)
            if resolved is None:
                continue
            target_path, category, element_id, _option_id = resolved
            mentioned.add((target_path, category, element_id))
            # Each sub-analysis along the target path is implicitly mentioned.
            for i in range(len(target_path)):
                mentioned.add((target_path[:i], "analyses", target_path[i]))
    for sub_id, sub_node in (node.get("analyses") or {}).items():
        _collect_mentioned(sub_node, path + (sub_id,), root, mentioned)


def _walk_coverage(
    node: dict[str, Any],
    path: tuple[str, ...],
    mentioned: set[tuple[tuple[str, ...], str, str]],
    warnings: list[NarrativeWarning],
) -> None:
    base = _node_path_str(path)

    for did, decision in (node.get("decisions") or {}).items():
        # Pure references to parent decisions aren't local elements.
        if isinstance(decision, dict) and decision.get("from"):
            continue
        if (path, "decisions", did) not in mentioned:
            p = f"{base}.decisions.{did}" if base else f"decisions.{did}"
            warnings.append(
                NarrativeWarning(
                    "NARRATIVE_UNMENTIONED",
                    f"Decision '{did}' is not mentioned in any narrative",
                    p,
                )
            )

    for fid in node.get("findings") or {}:
        if (path, "findings", fid) not in mentioned:
            p = f"{base}.findings.{fid}" if base else f"findings.{fid}"
            warnings.append(
                NarrativeWarning(
                    "NARRATIVE_UNMENTIONED",
                    f"Finding '{fid}' is not mentioned in any narrative",
                    p,
                )
            )

    for out in node.get("outputs") or []:
        oid = out.get("id")
        if not oid:
            continue
        if (path, "outputs", oid) not in mentioned:
            p = f"{base}.outputs.{oid}" if base else f"outputs.{oid}"
            warnings.append(
                NarrativeWarning(
                    "NARRATIVE_UNMENTIONED",
                    f"Output '{oid}' is not mentioned in any narrative",
                    p,
                )
            )

    for sub_id in node.get("analyses") or {}:
        if (path, "analyses", sub_id) not in mentioned:
            p = f"{base}.analyses.{sub_id}" if base else f"analyses.{sub_id}"
            warnings.append(
                NarrativeWarning(
                    "NARRATIVE_UNMENTIONED",
                    f"Sub-analysis '{sub_id}' is not mentioned in any narrative",
                    p,
                )
            )

    for sub_id, sub_node in (node.get("analyses") or {}).items():
        _walk_coverage(sub_node, path + (sub_id,), mentioned, warnings)


def validate_narrative_anchors_file(path: str | Path) -> list[SemanticError]:
    """Load and run anchor validation on a YAML file."""
    from astra.helpers import load_yaml

    path = Path(path)
    return validate_narrative_anchors(load_yaml(path), base_path=path.parent)


def check_narrative_coverage_file(path: str | Path) -> list[NarrativeWarning]:
    """Load and run coverage check on a YAML file."""
    from astra.helpers import load_yaml

    path = Path(path)
    return check_narrative_coverage(load_yaml(path), base_path=path.parent)
