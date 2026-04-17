"""Tests for narrative anchor resolution and coverage checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from astra.validation.narrative import (
    check_narrative_coverage,
    check_narrative_coverage_file,
    validate_narrative_anchors,
    validate_narrative_anchors_file,
)


def _minimal_with_narrative(narrative: Any) -> dict[str, Any]:
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
            {
                "abstract": (
                    "Refs: [method](#decisions.method), "
                    "[option](#decisions.method.options.a), "
                    "[output](#outputs.y), "
                    "[input](#inputs.x)."
                )
            }
        )
        assert validate_narrative_anchors(data) == []

    def test_broken_decision(self) -> None:
        data = _minimal_with_narrative({"abstract": "[missing](#decisions.nope)"})
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "BROKEN_NARRATIVE_ANCHOR"

    def test_broken_option(self) -> None:
        data = _minimal_with_narrative(
            {"abstract": "[missing opt](#decisions.method.options.zz)"}
        )
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "BROKEN_NARRATIVE_ANCHOR"

    def test_invalid_grammar_unknown_category(self) -> None:
        data = _minimal_with_narrative({"abstract": "[bad](#nope.foo)"})
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_NARRATIVE_ANCHOR"

    def test_invalid_grammar_category_without_id(self) -> None:
        data = _minimal_with_narrative({"abstract": "[bad](#decisions)"})
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_NARRATIVE_ANCHOR"

    def test_sub_analysis_path_anchor(self) -> None:
        data = _minimal_with_narrative({"abstract": "[s](#sub.decisions.d)"})
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
        data = _minimal_with_narrative({"abstract": "(placeholder)"})
        data["analyses"] = {
            "sub": {
                "narrative": {"m": "[parent method](#../decisions.method)"},
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
            }
        }
        assert validate_narrative_anchors(data) == []

    def test_escape_past_root_fails(self) -> None:
        data = _minimal_with_narrative({"abstract": "[x](#../decisions.method)"})
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].code == "BROKEN_NARRATIVE_ANCHOR"

    def test_accepts_narrative_section_object_form(self) -> None:
        # Simple-dict form accepts both bare string and {content: ...}.
        data = _minimal_with_narrative(
            {"abstract": {"content": "[method](#decisions.method)"}}
        )
        assert validate_narrative_anchors(data) == []

    def test_multiple_anchors_one_broken(self) -> None:
        data = _minimal_with_narrative(
            {"abstract": "[ok](#decisions.method) and [bad](#findings.x)"}
        )
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert "findings.x" in errs[0].message


class TestCoverage:
    def test_full_coverage_no_warnings(self, valid_dir: Path) -> None:
        warnings = check_narrative_coverage_file(valid_dir / "narrative_full_coverage.yaml")
        assert warnings == []

    def test_empty_narrative_flags_everything(self) -> None:
        data = _minimal_with_narrative({"abstract": "no refs"})
        warnings = check_narrative_coverage(data)
        codes = {(w.code, w.message) for w in warnings}
        assert any("Decision 'method'" in m for _, m in codes)
        assert any("Output 'y'" in m for _, m in codes)

    def test_coverage_ignores_inputs_and_options(self) -> None:
        # Only decisions/findings/outputs/analyses are coverage-checked.
        data = _minimal_with_narrative(
            {"abstract": "[m](#decisions.method) [o](#outputs.y)"}
        )
        warnings = check_narrative_coverage(data)
        # No warning for inputs.x or decisions.method.options.*.
        assert warnings == []

    def test_descendant_ref_covers_sub_analysis(self) -> None:
        data = _minimal_with_narrative(
            {"abstract": "[d](#decisions.method) [o](#outputs.y) [sub](#sub.decisions.d)"}
        )
        data["analyses"] = {
            "sub": {
                "narrative": {"a": "[d](#decisions.d) [o](#outputs.y)"},
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
            {"abstract": "[d](#decisions.method) [o](#outputs.y) [sub](#analyses.sub)"}
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

    def test_from_ref_decision_not_required_to_be_mentioned(self) -> None:
        data = _minimal_with_narrative(
            {"abstract": "[d](#decisions.method) [o](#outputs.y)"}
        )
        data["analyses"] = {
            "sub": {
                "narrative": {"a": "[o](#outputs.y)"},
                "inputs": [{"id": "x", "type": "data"}],
                "outputs": [{"id": "y", "type": "metric"}],
                "decisions": {
                    # Pure reference to parent — shouldn't require local mention.
                    "method": {"from": "../method"}
                },
            }
        }
        # Root covers analyses.sub via #analyses.sub? No — root mentions
        # #decisions.method but not #analyses.sub or any descendant. Add a
        # reference so sub-analysis coverage is satisfied.
        data["narrative"]["abstract"] += " [s](#sub.outputs.y)"
        warnings = check_narrative_coverage(data)
        paths = {w.path for w in warnings}
        # The from-ref'd decision must not appear as an uncovered element.
        assert "analyses.sub.decisions.method" not in paths


class TestFileHelpers:
    def test_validate_file_on_valid(self, valid_dir: Path) -> None:
        assert validate_narrative_anchors_file(valid_dir / "narrative_full_coverage.yaml") == []

    def test_validate_file_on_broken(self, invalid_dir: Path) -> None:
        errs = validate_narrative_anchors_file(invalid_dir / "narrative_broken_anchor.yaml")
        assert len(errs) == 2
        assert all(e.code == "BROKEN_NARRATIVE_ANCHOR" for e in errs)
