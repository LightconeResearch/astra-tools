"""Narrative validation for ASTRA specifications.

Two checks layered on top of structural and semantic validation:

1. **Anchor resolution** — Markdown links inside narrative prose of
   the form ``[text](#target)`` must resolve to a declared element.
   Broken references are errors.

2. **Coverage** — each Analysis node's own decisions, findings,
   outputs, and sub-analyses should be mentioned somewhere in the
   narrative tree. References may appear anywhere across the tree;
   unmentioned elements emit warnings (not errors).

Anchor grammar is **tree-path-first**, matching the rest of ASTRA's
reference syntax (``sibling.output_id`` in ``from``). Sub-analyses
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
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astra.helpers import load_yaml, resolve_analysis_tree
from astra.validation.semantic import SemanticError

_HREF_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# Image-syntax variant — `![alt](href)` — used for figure embeds in
# rendered narrative. The renderer treats a standalone-line image
# whose href is `#outputs.<id>` as an inline preview of that output;
# the validator enforces shape regardless of position.
_IMAGE_HREF_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
# Non-canonical "../" before "#" — the spec-canonical form puts the parent
# escape inside the fragment (e.g. (#../decisions.foo), not (../#decisions.foo)).
_PARENT_PATH_FORM_RE = re.compile(r"^(?:\.\./)+#")

# Output types that have a visual preview in the renderer. Image syntax
# pointing at an output of any other type would silently fall through to
# a plain link — almost certainly an author mistake, so the validator
# rejects it.
_PREVIEWABLE_OUTPUT_TYPES = frozenset({"figure", "table", "metric"})

_CATEGORIES = frozenset(
    {"inputs", "outputs", "decisions", "findings", "prior_insights", "analyses"}
)

# Categories whose elements are coverage-checked, with the human-readable
# label used in warnings. Options, inputs, and prior_insights are
# intentionally excluded: options are typically numerous, inputs are
# often trivially "the data", and prior_insights exist to justify
# decisions rather than being independently noteworthy.
_COVERAGE_CATEGORY_LABELS: dict[str, str] = {
    "decisions": "Decision",
    "findings": "Finding",
    "outputs": "Output",
    "analyses": "Sub-analysis",
}


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


def _narrative_text(node: dict[str, Any]) -> str:
    """Return the narrative blob for a node, or empty string if missing/wrong type."""
    n = node.get("narrative")
    return n if isinstance(n, str) else ""


def _extract_hrefs(text: str) -> Iterator[str]:
    """Yield every Markdown link href in the prose."""
    yield from _HREF_RE.findall(text)


def _node_path_str(path: tuple[str, ...]) -> str:
    """Render an absolute node path like ``analyses.foo.analyses.bar``."""
    return ".".join(f"analyses.{seg}" for seg in path)


def _narrative_report_path(base: str) -> str:
    """Build the path string used in error/warning reports for a narrative location."""
    return f"{base}.narrative" if base else "narrative"


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
    text = _narrative_text(node)
    if text:
        narrative_path = _narrative_report_path(_node_path_str(path))
        for href in _extract_hrefs(text):
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

    A reference anywhere in the tree counts toward the target element's
    coverage. Mentioning a descendant implicitly mentions each
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
    text = _narrative_text(node)
    if text:
        for href in _extract_hrefs(text):
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


def _iter_coverage_ids(node: dict[str, Any], category: str) -> Iterator[str]:
    """Yield element IDs for a coverage-checked category on a single node."""
    if category == "decisions":
        for did, decision in (node.get("decisions") or {}).items():
            # Pure references to parent decisions aren't local elements.
            if isinstance(decision, dict) and decision.get("from"):
                continue
            yield did
    elif category == "outputs":
        for out in node.get("outputs") or []:
            oid = out.get("id")
            if oid:
                yield oid
    else:  # "findings" or "analyses"
        yield from (node.get(category) or {})


def _walk_coverage(
    node: dict[str, Any],
    path: tuple[str, ...],
    mentioned: set[tuple[tuple[str, ...], str, str]],
    warnings: list[NarrativeWarning],
) -> None:
    base = _node_path_str(path)
    for category, label in _COVERAGE_CATEGORY_LABELS.items():
        for eid in _iter_coverage_ids(node, category):
            if (path, category, eid) in mentioned:
                continue
            element_path = f"{base}.{category}.{eid}" if base else f"{category}.{eid}"
            warnings.append(
                NarrativeWarning(
                    "NARRATIVE_UNMENTIONED",
                    f"{label} '{eid}' is not mentioned in any narrative",
                    element_path,
                )
            )
    for sub_id, sub_node in (node.get("analyses") or {}).items():
        _walk_coverage(sub_node, path + (sub_id,), mentioned, warnings)


def validate_narrative_figure_embeds(
    data: dict[str, Any], base_path: Path | None = None
) -> list[SemanticError]:
    """Enforce figure-embed shape on Markdown image syntax.

    Image syntax (``![alt](href)``) in narrative prose means "embed
    this artefact" to the renderer. Author mistakes show up as image
    syntax pointing at the wrong kind of thing; this validator rejects
    them so they don't degrade silently to a broken link.

    Errors:

    - **External URL**: image href that isn't an anchor (no leading
      ``#``). Narrative figures should reference the analysis's own
      outputs, not external pictures.
    - **Wrong category**: image href that resolves to a decision /
      finding / input / sub-analysis / option, not an output. Only
      outputs are artefacts.
    - **Non-previewable output**: image href that resolves to an
      output whose type isn't ``figure``, ``table``, or ``metric``
      (the previewable set). The renderer can't show a preview, so
      the embed would degrade to a plain link.

    Anchor-grammar errors and broken-anchor errors are already reported
    by ``validate_narrative_anchors``; this validator skips unparseable
    or unresolvable hrefs to avoid duplicate diagnostics.
    """
    if base_path is not None:
        data = resolve_analysis_tree(data, base_path)
    errors: list[SemanticError] = []
    _walk_figure_embeds(data, (), data, errors)
    return errors


def _output_type(node: dict[str, Any], output_id: str) -> str | None:
    """Return the declared ``type`` for ``output_id`` on ``node``, or None."""
    for out in node.get("outputs") or []:
        if out.get("id") == output_id:
            t = out.get("type")
            return t if isinstance(t, str) else None
    return None


def _walk_figure_embeds(
    node: dict[str, Any],
    path: tuple[str, ...],
    root: dict[str, Any],
    errors: list[SemanticError],
) -> None:
    text = _narrative_text(node)
    if text:
        narrative_path = _narrative_report_path(_node_path_str(path))
        for href in _IMAGE_HREF_RE.findall(text):
            if not href.startswith("#"):
                errors.append(
                    SemanticError(
                        "INVALID_FIGURE_EMBED",
                        f"Figure embed '{href}' must reference an analysis "
                        f"output (e.g. '#outputs.<id>'), not an external URL",
                        narrative_path,
                    )
                )
                continue
            raw = href[1:]
            if "." not in raw:
                # Dotless anchor — bare Markdown heading link, not an
                # ASTRA reference. Image syntax pointing at one is
                # still nonsense (no artefact to embed), so flag it.
                errors.append(
                    SemanticError(
                        "INVALID_FIGURE_EMBED",
                        f"Figure embed '#{raw}' must reference an output (e.g. '#outputs.<id>')",
                        narrative_path,
                    )
                )
                continue
            parsed = _parse_anchor(raw)
            if parsed is None:
                # Anchor-grammar errors are reported by
                # validate_narrative_anchors — skip to avoid duplicate
                # diagnostics on the same href.
                continue
            resolved = _resolve_anchor(parsed, path, root)
            if resolved is None:
                # Same — broken-anchor errors are reported elsewhere.
                continue
            target_path, category, element_id, option_id = resolved
            if category != "outputs" or option_id is not None:
                errors.append(
                    SemanticError(
                        "INVALID_FIGURE_EMBED",
                        f"Figure embed '#{raw}' targets a {category} entry; "
                        f"image syntax may only reference outputs",
                        narrative_path,
                    )
                )
                continue
            target_node = _get_node_at(root, target_path)
            out_type = _output_type(target_node or {}, element_id) or "data"
            if out_type not in _PREVIEWABLE_OUTPUT_TYPES:
                errors.append(
                    SemanticError(
                        "INVALID_FIGURE_EMBED",
                        f"Figure embed '#{raw}' targets output '{element_id}' "
                        f"of type '{out_type}', which has no preview; "
                        f"figure embeds require type figure, table, or metric",
                        narrative_path,
                    )
                )
    for sub_id, sub_node in (node.get("analyses") or {}).items():
        _walk_figure_embeds(sub_node, path + (sub_id,), root, errors)


def validate_narrative_figure_embeds_file(path: str | Path) -> list[SemanticError]:
    """Load and run figure-embed validation on a YAML file."""
    path = Path(path)
    return validate_narrative_figure_embeds(load_yaml(path), base_path=path.parent)


def validate_narrative_anchors_file(path: str | Path) -> list[SemanticError]:
    """Load and run anchor validation on a YAML file."""
    path = Path(path)
    return validate_narrative_anchors(load_yaml(path), base_path=path.parent)


def check_narrative_coverage_file(path: str | Path) -> list[NarrativeWarning]:
    """Load and run coverage check on a YAML file."""
    path = Path(path)
    return check_narrative_coverage(load_yaml(path), base_path=path.parent)
