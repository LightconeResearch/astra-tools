"""Core verification logic for ASTRA insights.

Verifies that evidence (quotes, figures, tables) exists in source documents.
Now uses DOI-based paper cache instead of arXiv sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from astra.papers.cache import PaperCache
from astra.verification.cache import VerificationCache
from astra.verification.pdf import PDFDocument, extract_text_from_pdf


class VerificationStatus(StrEnum):
    """Status of a verification check."""

    VERIFIED = "verified"  # Evidence found in source
    NOT_FOUND = "not_found"  # Evidence not found in source
    SKIPPED = "skipped"  # Could not verify (e.g., figure/table)
    CACHED = "cached"  # Verified from cache (no re-check needed)
    ERROR = "error"  # Error during verification


@dataclass
class EvidenceVerification:
    """Result of verifying a single piece of evidence.

    Attributes:
        evidence_id: ID of the evidence being verified.
        doi: DOI of the paper.
        version: Paper version (for arXiv).
        status: Overall verification status.
        quote_status: Status of quote verification (if quote present).
        quote_found_pages: Pages where quote was found (1-indexed).
        expected_page: Expected page from location hint.
        message: Human-readable description of result.
        from_cache: Whether result came from cache.
    """

    evidence_id: str
    doi: str
    version: int | None = None
    status: VerificationStatus = VerificationStatus.VERIFIED
    quote_status: VerificationStatus | None = None
    quote_found_pages: list[int] = field(default_factory=list)
    expected_page: int | None = None
    message: str = ""
    from_cache: bool = False

    @property
    def is_valid(self) -> bool:
        """Check if evidence is verified or skipped (not an error)."""
        return self.status in (
            VerificationStatus.VERIFIED,
            VerificationStatus.SKIPPED,
            VerificationStatus.CACHED,
        )


@dataclass
class InsightVerification:
    """Result of verifying all evidence for an insight.

    Attributes:
        insight_id: ID of the insight being verified.
        evidence_results: Verification results for each piece of evidence.
        overall_status: Overall verification status.
    """

    insight_id: str
    evidence_results: list[EvidenceVerification] = field(default_factory=list)
    overall_status: VerificationStatus = VerificationStatus.VERIFIED

    @property
    def is_valid(self) -> bool:
        """Check if all evidence is valid."""
        return all(ev.is_valid for ev in self.evidence_results)

    @property
    def verified_count(self) -> int:
        """Count of verified evidence items."""
        return sum(
            1
            for ev in self.evidence_results
            if ev.status in (VerificationStatus.VERIFIED, VerificationStatus.CACHED)
        )

    @property
    def failed_count(self) -> int:
        """Count of failed evidence items."""
        return sum(1 for ev in self.evidence_results if not ev.is_valid)

    @property
    def cached_count(self) -> int:
        """Count of cached evidence items."""
        return sum(1 for ev in self.evidence_results if ev.from_cache)


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Get attribute from dict or object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _skip_if_no_paper(evidence: Any) -> EvidenceVerification | None:
    """Return a SKIPPED EvidenceVerification for evidence that has no paper backing.

    Some evidence (typically findings.evidence) references an `artifact:` (output ID)
    rather than a paper DOI — there is no document to search, so paper-cache lookup
    would spuriously return ERROR ("Paper not in cache"). Mark these SKIPPED so the
    gap is visible in the summary instead of being reported as a failure.

    Returns None if the evidence has a DOI (normal paper-backed verification path).
    """
    doi = _get_attr(evidence, "doi", "")
    if doi:
        return None
    if _get_attr(evidence, "artifact"):
        artifact_id = _get_attr(evidence, "artifact", "unknown")
        return EvidenceVerification(
            evidence_id=_get_attr(evidence, "id", "unknown"),
            doi="",
            version=_get_attr(evidence, "version"),
            status=VerificationStatus.SKIPPED,
            message=f"Artifact quote verification not yet implemented: {artifact_id}",
        )
    return None


def _determine_overall_status(results: list[EvidenceVerification]) -> VerificationStatus:
    """Determine overall verification status from individual results.

    Priority order: ERROR > NOT_FOUND > SKIPPED > VERIFIED
    """
    statuses = {r.status for r in results}

    # Check in priority order
    for status in (
        VerificationStatus.ERROR,
        VerificationStatus.NOT_FOUND,
    ):
        if status in statuses:
            return status

    # If all are skipped or cached, return SKIPPED
    if statuses <= {VerificationStatus.SKIPPED, VerificationStatus.CACHED}:
        return VerificationStatus.SKIPPED

    return VerificationStatus.VERIFIED


def verify_quote_in_pdf(
    quote_text: str,
    pdf: PDFDocument,
    page_hint: int | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
) -> tuple[VerificationStatus, list[int], str]:
    """Verify a quote exists in a PDF.

    Args:
        quote_text: The quote text to find.
        pdf: PDFDocument with extracted text.
        page_hint: Optional page hint (1-indexed) to optimize search.
            This is only used to prioritize search order, not for validation.
        prefix: Optional text before the quote (for disambiguation per W3C TextQuoteSelector).
        suffix: Optional text after the quote (for disambiguation per W3C TextQuoteSelector).

    Returns:
        Tuple of (status, found_pages, message).
    """
    found_pages = pdf.find_quote(quote_text, page=page_hint, prefix=prefix, suffix=suffix)

    if not found_pages:
        return VerificationStatus.NOT_FOUND, [], f"Quote not found in PDF: '{quote_text[:50]}...'"

    return VerificationStatus.VERIFIED, found_pages, f"Quote verified on page(s) {found_pages}"


def verify_evidence(
    evidence: Any,
    pdf: PDFDocument,
    verification_cache: VerificationCache | None = None,
) -> EvidenceVerification:
    """Verify a single piece of evidence against a PDF.

    Args:
        evidence: The evidence to verify (dict or Evidence object).
        pdf: PDFDocument with extracted text.
        verification_cache: Optional cache for verification results.

    Returns:
        EvidenceVerification with results.
    """
    evidence_id = _get_attr(evidence, "id", "unknown")
    doi = _get_attr(evidence, "doi", "")
    version = _get_attr(evidence, "version")
    location = _get_attr(evidence, "location")
    expected_page = _get_attr(location, "page") if location else None

    result = EvidenceVerification(
        evidence_id=evidence_id,
        doi=doi,
        version=version,
        status=VerificationStatus.VERIFIED,
        expected_page=expected_page,
    )

    # Check quote if present
    quote = _get_attr(evidence, "quote")
    if quote:
        quote_text = _get_attr(quote, "exact", "")
        quote_prefix = _get_attr(quote, "prefix")
        quote_suffix = _get_attr(quote, "suffix")

        # Check cache first
        if verification_cache:
            cached = verification_cache.get(doi, version, quote_text, pdf.sha256)
            if cached:
                result.status = VerificationStatus.CACHED
                result.quote_status = VerificationStatus(cached.status)
                result.quote_found_pages = cached.found_pages or []
                result.message = f"Verified from cache (status: {cached.status})"
                result.from_cache = True
                return result

        # Verify quote (page is used as search hint only, not for validation)
        # prefix/suffix from W3C TextQuoteSelector help disambiguate repeated quotes
        status, found_pages, message = verify_quote_in_pdf(
            quote_text, pdf, expected_page, quote_prefix, quote_suffix
        )
        result.quote_status = status
        result.status = status
        result.quote_found_pages = found_pages
        result.message = message

        # Cache result
        if verification_cache:
            verification_cache.set(
                doi=doi,
                version=version,
                quote_exact=quote_text,
                pdf_sha256=pdf.sha256,
                status=status.value,
                found_pages=found_pages,
                expected_page=expected_page,
            )

    # Figure/table verification - skip for now
    elif _get_attr(evidence, "figure"):
        figure = _get_attr(evidence, "figure")
        label = _get_attr(figure, "label", "unknown")
        result.status = VerificationStatus.SKIPPED
        result.message = f"Figure verification not yet implemented: {label}"

    elif _get_attr(evidence, "table"):
        table = _get_attr(evidence, "table")
        label = _get_attr(table, "label", "unknown")
        result.status = VerificationStatus.SKIPPED
        result.message = f"Table verification not yet implemented: {label}"

    elif _get_attr(evidence, "artifact"):
        # Artifact-backed evidence (typical for findings.evidence): the evidence
        # references an output ID rather than a paper DOI. At SPECIFY phase the
        # artifact is not materialized, so there is no document to search.
        # Mark SKIPPED so the gap is visible in the summary rather than silent.
        artifact_id = _get_attr(evidence, "artifact", "unknown")
        result.status = VerificationStatus.SKIPPED
        result.message = f"Artifact quote verification not yet implemented: {artifact_id}"

    return result


def verify_insight(
    insight: Any,
    paper_cache: PaperCache | None = None,
    verification_cache: VerificationCache | None = None,
) -> InsightVerification:
    """Verify all evidence for an insight.

    Uses the paper cache to find PDFs by DOI and verifies each piece of evidence.

    Args:
        insight: The insight to verify (dict or Insight object).
        paper_cache: Cache for downloaded papers.
        verification_cache: Cache for verification results.

    Returns:
        InsightVerification with results for all evidence.
    """
    if paper_cache is None:
        paper_cache = PaperCache()
    if verification_cache is None:
        verification_cache = VerificationCache()

    insight_id = _get_attr(insight, "id", "unknown")
    evidence_list = _get_attr(insight, "evidence", [])

    evidence_results: list[EvidenceVerification] = []

    # Group evidence by DOI/version for efficiency
    for ev in evidence_list:
        # Artifact-backed evidence (no paper DOI) cannot be verified against a PDF;
        # emit SKIPPED so the gap is visible instead of a spurious "paper not cached" error.
        skipped = _skip_if_no_paper(ev)
        if skipped is not None:
            evidence_results.append(skipped)
            continue

        evidence_id = _get_attr(ev, "id", "unknown")
        doi = _get_attr(ev, "doi", "")
        version = _get_attr(ev, "version")

        # Get PDF from cache
        cached_paper = paper_cache.get(doi, version)
        if not cached_paper:
            evidence_results.append(
                EvidenceVerification(
                    evidence_id=evidence_id,
                    doi=doi,
                    version=version,
                    status=VerificationStatus.ERROR,
                    message=f"Paper not in cache: {doi} (use 'astra paper add' first)",
                )
            )
            continue

        # Extract text from PDF
        try:
            pdf = extract_text_from_pdf(cached_paper.pdf_path)
        except Exception as e:
            evidence_results.append(
                EvidenceVerification(
                    evidence_id=evidence_id,
                    doi=doi,
                    version=version,
                    status=VerificationStatus.ERROR,
                    message=f"Failed to extract text from PDF: {e}",
                )
            )
            continue

        # Verify the evidence
        result = verify_evidence(ev, pdf, verification_cache)
        evidence_results.append(result)

    # Determine overall status (priority: ERROR > NOT_FOUND > SKIPPED > VERIFIED)
    overall = _determine_overall_status(evidence_results)

    return InsightVerification(
        insight_id=insight_id,
        evidence_results=evidence_results,
        overall_status=overall,
    )


def verify_all_insights(
    insights: dict[str, Any],
    paper_cache: PaperCache | None = None,
    verification_cache: VerificationCache | None = None,
) -> dict[str, InsightVerification]:
    """Verify all insights in an analysis.

    Args:
        insights: Dict mapping insight IDs to insight data.
        paper_cache: Cache for downloaded papers.
        verification_cache: Cache for verification results.

    Returns:
        Dict mapping insight IDs to verification results.
    """
    if paper_cache is None:
        paper_cache = PaperCache()
    if verification_cache is None:
        verification_cache = VerificationCache()

    # Pre-extract PDFs once per unique (DOI, version) to avoid redundant parsing.
    # This is critical for performance: a single 23MB PDF can take seconds to parse,
    # and without caching it would be re-parsed for every evidence item that references it.
    pdf_cache: dict[tuple[str, int | None], PDFDocument | None] = {}

    # Collect all unique (DOI, version) pairs across all insights
    for insight in insights.values():
        for ev in _get_attr(insight, "evidence", []):
            # Skip artifact-backed evidence (no DOI) — handled per-evidence below.
            if _skip_if_no_paper(ev) is not None:
                continue
            doi = _get_attr(ev, "doi", "")
            version = _get_attr(ev, "version")
            key = (doi, version)
            if key not in pdf_cache:
                cached_paper = paper_cache.get(doi, version)
                if cached_paper is None:
                    pdf_cache[key] = None
                else:
                    try:
                        pdf_cache[key] = extract_text_from_pdf(cached_paper.pdf_path)
                    except Exception:
                        pdf_cache[key] = None

    results = {}
    for insight_id, insight in insights.items():
        results[insight_id] = _verify_insight_with_pdf_cache(
            insight, paper_cache, verification_cache, pdf_cache
        )

    return results


def _verify_insight_with_pdf_cache(
    insight: Any,
    paper_cache: PaperCache,
    verification_cache: VerificationCache,
    pdf_cache: dict[tuple[str, int | None], PDFDocument | None],
) -> InsightVerification:
    """Verify all evidence for an insight using pre-extracted PDFs.

    Args:
        insight: The insight to verify (dict or Insight object).
        paper_cache: Cache for downloaded papers.
        verification_cache: Cache for verification results.
        pdf_cache: Pre-extracted PDF documents keyed by (DOI, version).

    Returns:
        InsightVerification with results for all evidence.
    """
    insight_id = _get_attr(insight, "id", "unknown")
    evidence_list = _get_attr(insight, "evidence", [])

    evidence_results: list[EvidenceVerification] = []

    for ev in evidence_list:
        # Artifact-backed evidence (no paper DOI) cannot be verified against a PDF;
        # emit SKIPPED so the gap is visible instead of a spurious "paper not cached" error.
        skipped = _skip_if_no_paper(ev)
        if skipped is not None:
            evidence_results.append(skipped)
            continue

        evidence_id = _get_attr(ev, "id", "unknown")
        doi = _get_attr(ev, "doi", "")
        version = _get_attr(ev, "version")
        key = (doi, version)

        pdf = pdf_cache.get(key)
        if pdf is None:
            # Check if paper exists but failed to parse vs not in cache
            cached_paper = paper_cache.get(doi, version)
            if not cached_paper:
                msg = f"Paper not in cache: {doi} (use 'astra paper add' first)"
            else:
                msg = f"Failed to extract text from PDF: {doi}"
            evidence_results.append(
                EvidenceVerification(
                    evidence_id=evidence_id,
                    doi=doi,
                    version=version,
                    status=VerificationStatus.ERROR,
                    message=msg,
                )
            )
            continue

        result = verify_evidence(ev, pdf, verification_cache)
        evidence_results.append(result)

    overall = _determine_overall_status(evidence_results)

    return InsightVerification(
        insight_id=insight_id,
        evidence_results=evidence_results,
        overall_status=overall,
    )
