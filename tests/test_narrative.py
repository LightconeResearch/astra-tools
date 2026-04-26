"""Tests for narrative anchor resolution and coverage checks."""

from __future__ import annotations

from pathlib import Path

from astra.validation.narrative import (
    check_narrative_coverage,
    check_narrative_coverage_file,
    validate_narrative_anchors,
    validate_narrative_anchors_file,
    validate_narrative_sections,
)

_FULL_SECTIONS = ("summary", "findings", "methods", "inputs", "outputs")


def _full_narrative(**overrides: str) -> dict[str, str]:
    """Build a narrative with placeholder prose in every section."""
    base = {s: f"{s} placeholder." for s in _FULL_SECTIONS}
    base.update(overrides)
    return base


def _minimal_with_narrative(narrative: dict[str, str] | str) -> dict[str, object]:
    """Build a minimal analysis. Shorthand: a bare string is placed in ``summary``."""
    if isinstance(narrative, str):
        narrative = {"summary": narrative}
    return {
        "version": "1.0",
        "name": "Test",
        "narrative": narrative,
        "inputs": [{"id": "x", "type": "data"}],
        "outputs": [{"id": "y", "type": "metric"}],
        "decisions": {
            "method": {
                "label": "Method",
                "rationale": "r",
                "default": "a",
                "options": {"a": {"label": "A"}, "b": {"label": "B"}},
            }
        },
    }


class TestAnchorResolution:
    def test_resolved_local_anchors(self) -> None:
        data = _minimal_with_narrative(
            "Refs: [method](#decisions.method), "
            "[option](#decisions.method.options.a), "
            "[output](#outputs.y), "
            "[input](#inputs.x)."
        )
        assert validate_narrative_anchors(data) == []

    def test_broken_decision(self) -> None:
        data = _minimal_with_narrative("[missing](#decisions.nope)")
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "BROKEN_NARRATIVE_ANCHOR"

    def test_broken_option(self) -> None:
        data = _minimal_with_narrative("[missing opt](#decisions.method.options.zz)")
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "BROKEN_NARRATIVE_ANCHOR"

    def test_invalid_grammar_unknown_category(self) -> None:
        data = _minimal_with_narrative("[bad](#nope.foo)")
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_NARRATIVE_ANCHOR"

    def test_dotless_category_treated_as_heading_link(self) -> None:
        # Dotless anchors are skipped as Markdown heading links, even when
        # the segment happens to be a reserved category name. This is a
        # known tradeoff of the silent-skip rule.
        data = _minimal_with_narrative("[bad](#decisions)")
        assert validate_narrative_anchors(data) == []

    def test_sub_analysis_path_anchor(self) -> None:
        data = _minimal_with_narrative("[s](#sub.decisions.d)")
        data["analyses"] = {
            "sub": {
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
                "decisions": {
                    "d": {
                        "label": "D",
                        "rationale": "r",
                        "default": "a",
                        "options": {"a": {"label": "A"}},
                    }
                },
            }
        }
        assert validate_narrative_anchors(data) == []

    def test_escape_to_parent(self) -> None:
        # Sub-analysis narrative references parent decision via ../.
        data = _minimal_with_narrative("(placeholder)")
        data["analyses"] = {
            "sub": {
                "narrative": {"summary": "[parent method](#../decisions.method)"},
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
            }
        }
        assert validate_narrative_anchors(data) == []

    def test_escape_past_root_fails(self) -> None:
        data = _minimal_with_narrative("[x](#../decisions.method)")
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "BROKEN_NARRATIVE_ANCHOR"

    def test_plain_markdown_heading_anchors_ignored(self) -> None:
        # Dotless anchors are Markdown heading links, not ASTRA refs.
        data = _minimal_with_narrative(
            "## Abstract\n[skip to results](#results) "
            "[method](#decisions.method)\n\n"
            "## Results\n[back to top](#abstract)"
        )
        assert validate_narrative_anchors(data) == []

    def test_plain_markdown_heading_anchors_dont_count_for_coverage(self) -> None:
        # A dotless anchor must not satisfy coverage for any element.
        data = _minimal_with_narrative("[bogus](#method) [o](#outputs.y)")
        warnings = check_narrative_coverage(data)
        codes = {w.message for w in warnings}
        assert any("Decision 'method'" in m for m in codes)

    def test_non_canonical_parent_escape_form_errors(self) -> None:
        # `../` BEFORE `#` is the wrong form. Spec-canonical is `#../...`.
        # Used to silently bypass validation; now flagged.
        data = _minimal_with_narrative("[bad](../#decisions.method)")
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_NARRATIVE_ANCHOR"
        assert "../" in errs[0].message

    def test_chained_non_canonical_parent_escape_errors(self) -> None:
        data = _minimal_with_narrative("[bad](../../#decisions.method)")
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_NARRATIVE_ANCHOR"

    def test_analyses_prefix_drill_in_emits_tailored_hint(self) -> None:
        # `#analyses.<sub>.<cat>.<id>` is the natural-but-wrong form authors
        # write when drilling into a sub-analysis. The correct form drops
        # the `analyses.` collection prefix: `#<sub>.<cat>.<id>`.
        data = _minimal_with_narrative("[bad](#analyses.sub.decisions.d)")
        data["analyses"] = {
            "sub": {
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
                "decisions": {
                    "d": {
                        "label": "D",
                        "rationale": "r",
                        "default": "a",
                        "options": {"a": {"label": "A"}},
                    }
                },
            }
        }
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_NARRATIVE_ANCHOR"
        assert "starts with 'analyses.<sub>'" in errs[0].message
        assert "#<sub>.<category>.<id>" in errs[0].message

    def test_analyses_prefix_drill_in_with_parent_escape_emits_tailored_hint(self) -> None:
        # Sibling reference written with the analyses-prefix anti-pattern:
        # `#../analyses.<sib>.<cat>.<id>`. The correct form is
        # `#../<sib>.<cat>.<id>`.
        data = _minimal_with_narrative("(placeholder)")
        data["analyses"] = {
            "sub": {
                "narrative": {"summary": "[bad](#../analyses.other.decisions.d)"},
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
            },
            "other": {
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
                "decisions": {
                    "d": {
                        "label": "D",
                        "rationale": "r",
                        "default": "a",
                        "options": {"a": {"label": "A"}},
                    }
                },
            },
        }
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_NARRATIVE_ANCHOR"
        assert "starts with 'analyses.<sub>'" in errs[0].message

    def test_analyses_node_reference_still_valid(self) -> None:
        # `#analyses.<sub>` (whole sub-analysis node, no further drill-in)
        # remains the canonical form and must not trigger the new hint.
        data = _minimal_with_narrative("[s](#analyses.sub)")
        data["analyses"] = {
            "sub": {
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
            }
        }
        assert validate_narrative_anchors(data) == []

    def test_external_links_ignored(self) -> None:
        # URLs and other non-anchor hrefs are not ASTRA references.
        data = _minimal_with_narrative(
            "See [paper](https://example.com/paper.pdf#page=3) and [other doc](./neighbor.md)."
        )
        assert validate_narrative_anchors(data) == []

    def test_multiple_anchors_one_broken(self) -> None:
        data = _minimal_with_narrative("[ok](#decisions.method) and [bad](#findings.x)")
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert "findings.x" in errs[0].message


class TestCoverage:
    def test_full_coverage_no_warnings(self, valid_dir: Path) -> None:
        warnings = check_narrative_coverage_file(valid_dir / "narrative_full_coverage.yaml")
        assert warnings == []

    def test_empty_narrative_flags_everything(self) -> None:
        data = _minimal_with_narrative("no refs")
        warnings = check_narrative_coverage(data)
        codes = {(w.code, w.message) for w in warnings}
        assert any("Decision 'method'" in m for _, m in codes)
        assert any("Output 'y'" in m for _, m in codes)

    def test_coverage_ignores_inputs_and_options(self) -> None:
        # Only decisions/findings/outputs/analyses are coverage-checked.
        data = _minimal_with_narrative("[m](#decisions.method) [o](#outputs.y)")
        warnings = check_narrative_coverage(data)
        # No warning for inputs.x or decisions.method.options.*.
        assert warnings == []

    def test_descendant_ref_covers_sub_analysis(self) -> None:
        data = _minimal_with_narrative(
            "[d](#decisions.method) [o](#outputs.y) [sub](#sub.decisions.d)"
        )
        data["analyses"] = {
            "sub": {
                "narrative": {"summary": "[d](#decisions.d) [o](#outputs.y)"},
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
                "decisions": {
                    "d": {
                        "label": "D",
                        "rationale": "r",
                        "default": "a",
                        "options": {"a": {"label": "A"}},
                    }
                },
            }
        }
        warnings = check_narrative_coverage(data)
        # Root-level: all covered. Sub-level: all covered.
        assert warnings == []

    def test_sub_analysis_uncovered_warns_at_sub_path(self) -> None:
        data = _minimal_with_narrative(
            "[d](#decisions.method) [o](#outputs.y) [sub](#analyses.sub)"
        )
        data["analyses"] = {
            "sub": {
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "z", "type": "metric"}],
            }
        }
        warnings = check_narrative_coverage(data)
        paths = {w.path for w in warnings}
        assert "analyses.sub.outputs.z" in paths

    def test_from_decision_not_required_to_be_mentioned(self) -> None:
        data = _minimal_with_narrative("[d](#decisions.method) [o](#outputs.y) [s](#sub.outputs.y)")
        data["analyses"] = {
            "sub": {
                "narrative": {"summary": "[o](#outputs.y)"},
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
                "decisions": {
                    # Pure reference to parent — shouldn't require local mention.
                    "method": {"from": "../method"}
                },
            }
        }
        warnings = check_narrative_coverage(data)
        paths = {w.path for w in warnings}
        # A parent-referenced decision must not appear as an uncovered element.
        assert "analyses.sub.decisions.method" not in paths


class TestFileHelpers:
    def test_validate_file_on_valid(self, valid_dir: Path) -> None:
        assert validate_narrative_anchors_file(valid_dir / "narrative_full_coverage.yaml") == []

    def test_validate_file_on_broken(self, invalid_dir: Path) -> None:
        errs = validate_narrative_anchors_file(invalid_dir / "narrative_broken_anchor.yaml")
        assert len(errs) == 2
        assert all(e.code == "BROKEN_NARRATIVE_ANCHOR" for e in errs)


class TestSectionedNarrative:
    """Anchors and coverage work the same when narrative is a dict of sections."""

    def test_anchors_across_sections_resolve(self) -> None:
        data = _minimal_with_narrative(
            _full_narrative(
                methods="[method](#decisions.method) with [option](#decisions.method.options.a)",
                outputs="See [output](#outputs.y).",
                inputs="See [input](#inputs.x).",
            )
        )
        assert validate_narrative_anchors(data) == []

    def test_broken_anchor_reports_section_path(self) -> None:
        data = _minimal_with_narrative(_full_narrative(findings="[bad](#decisions.nope)"))
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].path == "narrative.findings"

    def test_coverage_is_global_across_sections(self) -> None:
        # Decision cited in summary, output cited in outputs — both count.
        data = _minimal_with_narrative(
            _full_narrative(
                summary="Mentions [method](#decisions.method) up top.",
                outputs="Produces [y](#outputs.y).",
            )
        )
        assert check_narrative_coverage(data) == []


class TestNarrativeSections:
    """Section-requirement check: a section is required when the
    corresponding structured data exists on the Analysis node."""

    def test_full_narrative_no_errors(self) -> None:
        data = _minimal_with_narrative(_full_narrative())
        assert validate_narrative_sections(data) == []

    def test_missing_methods_when_decisions_present_errors(self) -> None:
        narrative = _full_narrative()
        del narrative["methods"]
        data = _minimal_with_narrative(narrative)
        errs = validate_narrative_sections(data)
        assert len(errs) == 1
        assert errs[0].code == "NARRATIVE_SECTION_REQUIRED"
        assert errs[0].path == "narrative.methods"
        assert "'decisions'" in errs[0].message

    def test_missing_inputs_section_errors(self) -> None:
        narrative = _full_narrative()
        del narrative["inputs"]
        data = _minimal_with_narrative(narrative)
        errs = validate_narrative_sections(data)
        assert len(errs) == 1
        assert errs[0].path == "narrative.inputs"

    def test_empty_section_treated_as_missing(self) -> None:
        data = _minimal_with_narrative(_full_narrative(outputs="   "))
        errs = validate_narrative_sections(data)
        paths = {e.path for e in errs}
        assert "narrative.outputs" in paths

    def test_summary_always_optional(self) -> None:
        narrative = _full_narrative()
        del narrative["summary"]
        data = _minimal_with_narrative(narrative)
        assert validate_narrative_sections(data) == []

    def test_missing_findings_section_ok_when_no_findings_declared(self) -> None:
        # The minimal fixture has no `findings:` key — so narrative.findings
        # is not required, even though it is absent from the narrative.
        narrative = _full_narrative()
        del narrative["findings"]
        data = _minimal_with_narrative(narrative)
        assert data.get("findings") is None
        assert validate_narrative_sections(data) == []

    def test_findings_section_required_when_finding_declared(self) -> None:
        narrative = _full_narrative()
        del narrative["findings"]
        data = _minimal_with_narrative(narrative)
        data["findings"] = {
            "f1": {
                "id": "f1",
                "claim": "A finding.",
                "created_at": "2026-01-01T00:00:00",
                "evidence": [],
            }
        }
        errs = validate_narrative_sections(data)
        assert len(errs) == 1
        assert errs[0].path == "narrative.findings"

    def test_methods_required_when_only_analyses_present(self) -> None:
        # A parent node with no decisions but with sub-analyses still
        # requires narrative.methods.
        data = {
            "version": "1.0",
            "name": "Test",
            "narrative": {"summary": "top"},
            "analyses": {
                "sub": {
                    "narrative": {"summary": "child"},
                }
            },
        }
        errs = validate_narrative_sections(data)
        assert any(e.path == "narrative.methods" and "'analyses'" in e.message for e in errs)

    def test_sub_analysis_requirements_checked(self) -> None:
        data = _minimal_with_narrative(_full_narrative())
        data["analyses"] = {
            "sub": {
                "narrative": {"summary": "only summary here"},
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
            }
        }
        errs = validate_narrative_sections(data)
        sub_paths = {e.path for e in errs if e.path and "analyses.sub" in e.path}
        # Only inputs and outputs required on the sub-analysis (no decisions,
        # no child analyses, no findings).
        assert sub_paths == {"analyses.sub.narrative.inputs", "analyses.sub.narrative.outputs"}
