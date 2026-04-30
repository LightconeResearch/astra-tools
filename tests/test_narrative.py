"""Tests for narrative anchor resolution and coverage checks."""

from __future__ import annotations

from pathlib import Path

from astra.validation.narrative import (
    check_narrative_coverage,
    check_narrative_coverage_file,
    validate_narrative_anchors,
    validate_narrative_anchors_file,
    validate_narrative_figure_embeds,
)


def _minimal_with_narrative(narrative: str) -> dict[str, object]:
    """Build a minimal analysis with the given narrative blob."""
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
                "narrative": "[parent method](#../decisions.method)",
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
                "narrative": "[d](#decisions.d) [o](#outputs.y)",
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
                "narrative": "[o](#outputs.y)",
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


class TestMarkdownHeadings:
    """Heading levels are render-time concerns; the validator just sees prose.
    These tests pin the contract: anchors and coverage work the same whether
    the prose is a single paragraph or carries `#`/`##`/`###` structure."""

    def test_anchors_resolve_under_h1_and_h2_and_h3(self) -> None:
        data = _minimal_with_narrative(
            "# Methods\n\n[method](#decisions.method) with "
            "[option](#decisions.method.options.a)\n\n"
            "## Inputs\n\nSee [input](#inputs.x).\n\n"
            "### Outputs\n\nSee [output](#outputs.y)."
        )
        assert validate_narrative_anchors(data) == []

    def test_broken_anchor_reports_narrative_path(self) -> None:
        data = _minimal_with_narrative("# Findings\n\n[bad](#decisions.nope)")
        errs = validate_narrative_anchors(data)
        assert len(errs) == 1
        assert errs[0].path == "narrative"

    def test_coverage_is_global_across_headings(self) -> None:
        # Decision cited in one section, output cited in another — both count.
        data = _minimal_with_narrative(
            "# Summary\n\nMentions [method](#decisions.method) up top.\n\n"
            "# Outputs\n\nProduces [y](#outputs.y)."
        )
        assert check_narrative_coverage(data) == []


class TestFigureEmbeds:
    """Image syntax (``![alt](href)``) means 'embed this artefact' to the
    renderer. The validator enforces that authors only point image syntax
    at previewable outputs; everything else is an author mistake that
    would silently degrade to a plain link or nothing at all."""

    def test_image_targeting_previewable_output_ok(self) -> None:
        # The minimal fixture's `y` output is a metric — previewable.
        data = _minimal_with_narrative("Here is the headline result:\n\n![accuracy](#outputs.y)")
        assert validate_narrative_figure_embeds(data) == []

    def test_image_targeting_decision_errors(self) -> None:
        data = _minimal_with_narrative("![the decision](#decisions.method)")
        errs = validate_narrative_figure_embeds(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_FIGURE_EMBED"
        assert "decisions" in errs[0].message
        assert errs[0].path == "narrative"

    def test_image_targeting_option_errors(self) -> None:
        data = _minimal_with_narrative("![option a](#decisions.method.options.a)")
        errs = validate_narrative_figure_embeds(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_FIGURE_EMBED"

    def test_image_targeting_input_errors(self) -> None:
        data = _minimal_with_narrative("![the input](#inputs.x)")
        errs = validate_narrative_figure_embeds(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_FIGURE_EMBED"

    def test_image_with_external_url_errors(self) -> None:
        data = _minimal_with_narrative("![logo](https://example.com/logo.png)")
        errs = validate_narrative_figure_embeds(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_FIGURE_EMBED"
        assert "external" in errs[0].message.lower()

    def test_image_targeting_non_previewable_output_errors(self) -> None:
        # Build an analysis with a `data`-typed output and reference it
        # via image syntax — should fail because data outputs have no
        # preview.
        data = {
            "version": "1.0",
            "name": "Test",
            "narrative": "![raw](#outputs.dump)",
            "inputs": [{"id": "x", "type": "data"}],
            "outputs": [{"id": "dump", "type": "data"}],
        }
        errs = validate_narrative_figure_embeds(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_FIGURE_EMBED"
        assert "data" in errs[0].message

    def test_image_with_broken_anchor_does_not_double_error(self) -> None:
        # Broken anchors are reported by validate_narrative_anchors;
        # the figure-embed validator should stay quiet so the same
        # mistake isn't reported twice.
        data = _minimal_with_narrative("![missing](#outputs.nope)")
        assert validate_narrative_figure_embeds(data) == []

    def test_image_with_invalid_grammar_does_not_double_error(self) -> None:
        data = _minimal_with_narrative("![weird](#nope.foo)")
        assert validate_narrative_figure_embeds(data) == []

    def test_image_in_sub_analysis_reports_sub_path(self) -> None:
        data = _minimal_with_narrative("(top placeholder)")
        data["analyses"] = {
            "sub": {
                "narrative": "![bad](#decisions.d)",
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
        errs = validate_narrative_figure_embeds(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_FIGURE_EMBED"
        assert errs[0].path == "analyses.sub.narrative"

    def test_inline_image_in_paragraph_still_validated(self) -> None:
        # Position-agnostic: even mid-paragraph image syntax is checked,
        # because the renderer's block-vs-inline rule is for rendering,
        # not validation. The author still meant to embed something.
        data = _minimal_with_narrative("Some prose, then ![bad](#decisions.method) more prose.")
        errs = validate_narrative_figure_embeds(data)
        assert len(errs) == 1
        assert errs[0].code == "INVALID_FIGURE_EMBED"

    def test_plain_text_link_to_decision_unaffected(self) -> None:
        # Text links to decisions are normal citations — only image
        # syntax is constrained to outputs.
        data = _minimal_with_narrative("[the method](#decisions.method)")
        assert validate_narrative_figure_embeds(data) == []
