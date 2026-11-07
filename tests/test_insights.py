"""§14 Insights and evidence: `INVALID_INSIGHT_REF`."""

from __future__ import annotations

from pathlib import Path

from astra import api
from tests.conftest import MINIMAL, repository

INSIGHTS = """\
prior_insights:
  insight2:
    claim: An earlier study found that decision1 changes the result.
    evidence:
      - doi: 10.5555/12345678
        location: {value: page=6}
findings:
  insight1:
    claim: Options a and b of decision1 give different results.
    evidence:
      - artifact: result
"""
"""§14's fragment, citing the analysis's own output."""


def cited(insights: str) -> str:
    """An analysis whose option `decision1.a` cites `insights`, a flow list."""
    return (
        MINIMAL
        + INSIGHTS
        + f"decisions:\n  decision1:\n    options:\n      a: {{insights: {insights}}}\n"
        + "      b: {}\n"
    )


def invalid(report: api.ValidationReport) -> list[tuple[str, str]]:
    return [
        (d.location.file, d.location.pointer)
        for d in report.diagnostics
        if d.code == "INVALID_INSIGHT_REF"
    ]


def test_an_option_citing_no_prior_insight_breaks_invalid_insight_ref(tmp_path: Path) -> None:
    """§14: an id that is no insight's, and a finding's, which isn't a prior insight; in a
    declared analysis's file too."""
    files = {
        "astra.yaml": cited("[insight2, insight9, insight1]") + "analyses: {sub: {path: sub}}\n",
        "sub/astra.yaml": cited("[insight3]"),
    }
    report = api.validate(repository(tmp_path, files))
    at = "/decisions/decision1/options/a/insights/"
    assert invalid(report) == [
        ("astra.yaml", f"{at}1"),
        ("astra.yaml", f"{at}2"),
        ("sub/astra.yaml", f"{at}0"),
    ]
    finding = next(d for d in report.diagnostics if d.location.pointer == f"{at}2")
    assert (finding.level, finding.location.line) == ("error", 22)
    assert "a finding" in finding.message


def test_an_option_citing_a_prior_insight_keeps_it(tmp_path: Path) -> None:
    """§14: `insights: [insight2]`."""
    files = {"astra.yaml": cited("[insight2]")}
    assert invalid(api.validate(repository(tmp_path, files))) == []
