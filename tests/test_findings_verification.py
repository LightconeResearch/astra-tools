"""Unit tests for findings.evidence verification and artifact-backed evidence skipping.

Covers the fix from PR ":astra validate --verify-evidence" walking findings.evidence
in addition to prior_insights.evidence, and the symmetric SKIPPED handling for
artifact-backed evidence (which has no paper to verify against).

These tests do not need network access — they construct in-memory PDFDocument
objects and dispatch through the verification machinery directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from astra.cli import main
from astra.verification.core import (
    VerificationStatus,
    verify_all_insights,
    verify_evidence,
)
from astra.verification.pdf import PDFDocument

# ---------------------------------------------------------------------------
# Stub paper cache: returns a pre-built PDFDocument by DOI/version
# ---------------------------------------------------------------------------


class _StubCachedPaper:
    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = pdf_path


class _StubPaperCache:
    """Minimal paper cache stand-in with optional pre-canned PDFs by (doi, version)."""

    def __init__(self, pdfs: dict[tuple[str, int | None], PDFDocument] | None = None) -> None:
        self._pdfs = pdfs or {}

    def get(self, doi: str, version: int | None = None) -> _StubCachedPaper | None:
        if (doi, version) in self._pdfs:
            # Path is unused by our stub extract_text monkeypatch; placeholder fine.
            return _StubCachedPaper(Path(f"/tmp/{doi.replace('/', '_')}.pdf"))
        return None


@pytest.fixture
def patch_extract(monkeypatch: pytest.MonkeyPatch):
    """Patch extract_text_from_pdf to return our pre-built PDFDocument."""

    def _install(pdfs: dict[tuple[str, int | None], PDFDocument]) -> _StubPaperCache:
        def fake_extract(_path: Path) -> PDFDocument:
            # Single-PDF fixtures: return the only one we have.
            return next(iter(pdfs.values()))

        monkeypatch.setattr("astra.verification.core.extract_text_from_pdf", fake_extract)
        return _StubPaperCache(pdfs)

    return _install


# ---------------------------------------------------------------------------
# Direct unit tests on verify_evidence + verify_all_insights
# ---------------------------------------------------------------------------


def test_artifact_evidence_returns_skipped_directly() -> None:
    """verify_evidence on artifact-backed evidence (no quote/figure/table) → SKIPPED."""
    pdf = PDFDocument(path=None, pages=[""], num_pages=1, sha256="x")  # type: ignore[arg-type]
    evidence = {"id": "ev1", "artifact": "trained_model"}
    result = verify_evidence(evidence, pdf)
    assert result.status == VerificationStatus.SKIPPED
    assert "Artifact quote verification not yet implemented" in result.message
    assert "trained_model" in result.message


def test_findings_with_artifact_evidence_skipped(patch_extract: Any) -> None:
    """verify_all_insights walks findings-shaped dict and skips artifact-only evidence."""
    paper_cache = patch_extract({})
    findings = {
        "result_a": {
            "id": "result_a",
            "claim": "Some result",
            "evidence": [
                {"id": "ev_a", "artifact": "accuracy_table"},
                {"id": "ev_b", "artifact": "f1_table"},
            ],
        }
    }
    results = verify_all_insights(findings, paper_cache=paper_cache)  # type: ignore[arg-type]

    assert "result_a" in results
    ev_results = results["result_a"].evidence_results
    assert len(ev_results) == 2
    assert all(ev.status == VerificationStatus.SKIPPED for ev in ev_results)
    assert all("Artifact quote verification" in ev.message for ev in ev_results)


def test_findings_with_paper_evidence_verified(patch_extract: Any) -> None:
    """findings.evidence backed by a paper DOI flows through normal verification."""
    pdf = PDFDocument(
        path=None,  # type: ignore[arg-type]
        pages=["The pipeline reproduces the canonical result within 1 percent."],
        num_pages=1,
        sha256="abc",
    )
    paper_cache = patch_extract({("10.9999/findings_paper", 1): pdf})

    findings = {
        "reproduction": {
            "id": "reproduction",
            "claim": "Pipeline reproduces the canonical result.",
            "evidence": [
                {
                    "id": "ev_paper",
                    "doi": "10.9999/findings_paper",
                    "version": 1,
                    "quote": {
                        "type": "TextQuoteSelector",
                        "exact": "The pipeline reproduces the canonical result within 1 percent.",
                    },
                }
            ],
        }
    }
    results = verify_all_insights(findings, paper_cache=paper_cache)  # type: ignore[arg-type]

    ev = results["reproduction"].evidence_results[0]
    assert ev.status in (VerificationStatus.VERIFIED, VerificationStatus.CACHED)


def test_prior_insights_still_walked(patch_extract: Any) -> None:
    """Regression guard: prior_insights verification is unchanged by the findings extension."""
    pdf = PDFDocument(
        path=None,  # type: ignore[arg-type]
        pages=["Prior result that was already verified."],
        num_pages=1,
        sha256="xyz",
    )
    paper_cache = patch_extract({("10.1234/prior", 2): pdf})

    prior = {
        "p1": {
            "id": "p1",
            "claim": "Prior result.",
            "evidence": [
                {
                    "id": "ev_p1",
                    "doi": "10.1234/prior",
                    "version": 2,
                    "quote": {
                        "type": "TextQuoteSelector",
                        "exact": "Prior result that was already verified.",
                    },
                }
            ],
        }
    }
    results = verify_all_insights(prior, paper_cache=paper_cache)  # type: ignore[arg-type]
    ev = results["p1"].evidence_results[0]
    assert ev.status in (VerificationStatus.VERIFIED, VerificationStatus.CACHED)


# ---------------------------------------------------------------------------
# CLI-level: validate --verify-evidence reports findings + artifact SKIPPED
# ---------------------------------------------------------------------------


def test_cli_validate_reports_findings_artifact_skipped(tmp_path: Path, patch_extract: Any) -> None:
    """`astra validate --verify-evidence` walks findings and reports SKIPPED (artifact)."""
    # No paper-backed PDFs needed: all evidence is artifact-backed.
    patch_extract({})

    yaml_text = """\
version: "1.0"
name: "Findings walk smoke test"
narrative:
  summary: |
    Smoke-test fixture for findings.evidence walk. The [result](#findings.result)
    is supported by an artifact-backed evidence item.
  methods: |
    A single [method decision](#decisions.method) governs the run.
  inputs: |
    Consumes the [data](#inputs.data) input.
  outputs: |
    Produces the [accuracy_table](#outputs.accuracy_table).
  findings: |
    Reports the [result](#findings.result).
inputs:
  - id: data
    type: data
outputs:
  - id: accuracy_table
    type: table
decisions:
  method:
    label: Method
    default: a
    options:
      a: {label: A}
      b: {label: B}
findings:
  result:
    id: result
    claim: "Method A is best."
    created_at: "2026-01-01T00:00:00Z"
    evidence:
      - id: ev_acc
        artifact: accuracy_table
"""
    analysis_path = tmp_path / "astra.yaml"
    analysis_path.write_text(yaml_text)

    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(analysis_path), "--verify-evidence"])

    assert result.exit_code == 0, result.output
    assert "Verifying evidence" in result.output
    assert "findings" in result.output
    assert "SKIPPED (artifact)" in result.output
    assert "Validation successful" in result.output
