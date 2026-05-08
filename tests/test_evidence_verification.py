"""Integration tests for evidence verification using a real arXiv paper.

Uses arXiv:1603.01599 "High Resolution Weak Lensing Mass-Mapping Combining
Shear and Flexion" by Lanusse et al.

These tests require network access and optional dependencies:
    pip install httpx pypdf

Run with: pytest tests/test_evidence_verification.py -v
"""

import shutil
import tempfile
from pathlib import Path

import pytest

# Check for optional dependencies
httpx = pytest.importorskip("httpx", reason="httpx required: pip install httpx")
pypdf = pytest.importorskip("pypdf", reason="pypdf required: pip install pypdf")

# Mark all tests as requiring network and verify deps
pytestmark = [
    pytest.mark.network,
    pytest.mark.slow,
]


# Test paper details
ARXIV_ID = "1603.01599"
DOI = f"10.48550/arXiv.{ARXIV_ID}"
VERSION = 1  # Use a specific version for reproducibility

# Real quote from the paper abstract
VALID_QUOTE = (
    "Including flexion allows us to supplement the shear on small scales "
    "in order to increase the sensitivity to substructures and the overall "
    "resolution of the convergence map."
)

# A fabricated quote that doesn't exist in the paper
FAKE_QUOTE = (
    "This paper proves that deep learning is always better than "
    "traditional methods for all scientific applications."
)


@pytest.fixture(scope="module")
def temp_cache_dir():
    """Create a temporary cache directory for tests."""
    cache_dir = Path(tempfile.mkdtemp(prefix="astra_test_cache_"))
    yield cache_dir
    # Cleanup after all tests in module
    shutil.rmtree(cache_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def paper_cache(temp_cache_dir):
    """Create a paper cache using temp directory."""
    from astra.papers.cache import PaperCache

    return PaperCache(cache_dir=temp_cache_dir / "papers")


@pytest.fixture(scope="module")
def verification_cache(temp_cache_dir):
    """Create a verification cache using temp directory."""
    from astra.verification.cache import VerificationCache

    return VerificationCache(cache_dir=temp_cache_dir / "verification")


@pytest.fixture(scope="module")
def downloaded_paper(paper_cache):
    """Download the test paper once for all tests."""
    from astra.papers.download import download_paper

    # Check if already in cache
    if paper_cache.has(DOI, VERSION):
        return paper_cache.get(DOI, VERSION)

    # Download the paper
    result = download_paper(DOI, VERSION)
    assert result.success, f"Failed to download paper: {result.error}"
    assert result.content is not None

    # Add to cache
    paper = paper_cache.add(
        doi=DOI,
        pdf_content=result.content,
        version=VERSION,
        source_url=result.url,
    )
    return paper


class TestPaperDownload:
    """Tests for paper downloading and caching."""

    def test_download_arxiv_paper(self, downloaded_paper):
        """Test that we can download an arXiv paper."""
        assert downloaded_paper is not None
        assert downloaded_paper.pdf_path.exists()
        assert downloaded_paper.metadata.doi == DOI
        assert downloaded_paper.metadata.version == VERSION
        assert len(downloaded_paper.metadata.sha256) == 64  # SHA-256 hex

    def test_paper_is_cached(self, paper_cache, downloaded_paper):
        """Test that downloaded paper is in cache."""
        assert paper_cache.has(DOI, VERSION)
        cached = paper_cache.get(DOI, VERSION)
        assert cached is not None
        assert cached.pdf_path == downloaded_paper.pdf_path

    def test_cache_returns_same_path(self, paper_cache):
        """Test that cache returns consistent paths."""
        path1 = paper_cache.get_path(DOI, VERSION)
        path2 = paper_cache.get_path(DOI, VERSION)
        assert path1 == path2


class TestPDFExtraction:
    """Tests for PDF text extraction."""

    def test_extract_text_from_pdf(self, downloaded_paper):
        """Test that we can extract text from the PDF."""
        from astra.verification.pdf import extract_text_from_pdf

        pdf = extract_text_from_pdf(downloaded_paper.pdf_path)
        assert pdf.num_pages > 0
        assert len(pdf.pages) == pdf.num_pages
        assert pdf.sha256 == downloaded_paper.metadata.sha256

    def test_find_valid_quote(self, downloaded_paper):
        """Test that we can find a real quote in the paper."""
        from astra.verification.pdf import extract_text_from_pdf

        pdf = extract_text_from_pdf(downloaded_paper.pdf_path)
        found_pages = pdf.find_quote(VALID_QUOTE)
        assert len(found_pages) > 0, f"Quote not found in paper: {VALID_QUOTE[:50]}..."

    def test_fake_quote_not_found(self, downloaded_paper):
        """Test that a fake quote is not found."""
        from astra.verification.pdf import extract_text_from_pdf

        pdf = extract_text_from_pdf(downloaded_paper.pdf_path)
        found_pages = pdf.find_quote(FAKE_QUOTE)
        assert len(found_pages) == 0, "Fake quote should not be found"


class TestEvidenceVerification:
    """Tests for evidence verification."""

    def test_verify_valid_evidence(self, paper_cache, verification_cache):
        """Test verification of valid evidence succeeds."""
        from astra.verification.core import VerificationStatus, verify_insight

        insight = {
            "id": "test_insight",
            "claim": "Flexion improves weak lensing mass mapping",
            "evidence": [
                {
                    "id": "ev1",
                    "doi": DOI,
                    "version": VERSION,
                    "quote": {
                        "type": "TextQuoteSelector",
                        "exact": VALID_QUOTE,
                    },
                }
            ],
        }

        result = verify_insight(insight, paper_cache, verification_cache)
        assert result.is_valid
        assert result.overall_status in (
            VerificationStatus.VERIFIED,
            VerificationStatus.CACHED,
        )
        assert len(result.evidence_results) == 1
        assert result.evidence_results[0].status in (
            VerificationStatus.VERIFIED,
            VerificationStatus.CACHED,
        )

    def test_verify_fake_evidence_fails(self, paper_cache, verification_cache):
        """Test verification of fake evidence fails."""
        from astra.verification.core import VerificationStatus, verify_insight

        insight = {
            "id": "fake_insight",
            "claim": "A fabricated claim",
            "evidence": [
                {
                    "id": "ev_fake",
                    "doi": DOI,
                    "version": VERSION,
                    "quote": {
                        "type": "TextQuoteSelector",
                        "exact": FAKE_QUOTE,
                    },
                }
            ],
        }

        result = verify_insight(insight, paper_cache, verification_cache)
        assert not result.is_valid
        assert result.overall_status == VerificationStatus.NOT_FOUND
        assert result.evidence_results[0].status == VerificationStatus.NOT_FOUND

    def test_verification_caching(self, paper_cache, verification_cache):
        """Test that verification results are cached."""
        from astra.verification.core import verify_insight

        insight = {
            "id": "cached_insight",
            "claim": "Testing cache",
            "evidence": [
                {
                    "id": "ev_cached",
                    "doi": DOI,
                    "version": VERSION,
                    "quote": {
                        "type": "TextQuoteSelector",
                        "exact": VALID_QUOTE,
                    },
                }
            ],
        }

        # First verification - should verify
        result1 = verify_insight(insight, paper_cache, verification_cache)
        assert result1.is_valid

        # Second verification - should come from cache
        result2 = verify_insight(insight, paper_cache, verification_cache)
        assert result2.is_valid
        assert result2.evidence_results[0].from_cache

    def test_missing_paper_error(self, verification_cache, temp_cache_dir):
        """Test error when paper is not in cache."""
        from astra.papers.cache import PaperCache
        from astra.verification.core import VerificationStatus, verify_insight

        # Use empty cache
        empty_cache = PaperCache(cache_dir=temp_cache_dir / "empty_papers")

        insight = {
            "id": "missing_paper_insight",
            "claim": "Test",
            "evidence": [
                {
                    "id": "ev_missing",
                    "doi": "10.48550/arXiv.9999.99999",  # Non-existent
                    "quote": {"type": "TextQuoteSelector", "exact": "test"},
                }
            ],
        }

        result = verify_insight(insight, empty_cache, verification_cache)
        assert not result.is_valid
        assert result.overall_status == VerificationStatus.ERROR
        assert "not in cache" in result.evidence_results[0].message


class TestFullValidationWorkflow:
    """Integration tests for the full validation workflow."""

    def test_validate_analysis_with_insights(self, paper_cache, temp_cache_dir):
        """Test validating an analysis file with insights and evidence."""
        from astra.helpers import load_yaml, save_yaml
        from astra.validation.schema import validate_analysis_schema
        from astra.validation.semantic import validate_analysis
        from astra.verification.cache import VerificationCache
        from astra.verification.core import verify_all_insights

        # Create a test analysis file
        analysis = {
            "version": "0.0.10",
            "name": "Test Analysis",
            "inputs": [{"id": "data", "type": "data"}],
            "outputs": [{"id": "result", "type": "metric"}],
            "decisions": {
                "method": {
                    "label": "Method",
                    "type": "method",
                    "default": "flexion",
                    "options": {
                        "flexion": {
                            "label": "Use flexion",
                            "insights": ["flexion_insight"],
                        },
                        "shear_only": {
                            "label": "Shear only",
                        },
                    },
                }
            },
            "prior_insights": {
                "flexion_insight": {
                    "id": "flexion_insight",
                    "claim": "Flexion improves weak lensing resolution",
                    "created_at": "2024-01-01T00:00:00Z",
                    "evidence": [
                        {
                            "id": "ev1",
                            "doi": DOI,
                            "version": VERSION,
                            "quote": {
                                "type": "TextQuoteSelector",
                                "exact": VALID_QUOTE,
                            },
                        }
                    ],
                }
            },
        }

        # Save to temp file
        analysis_path = temp_cache_dir / "test_analysis.yaml"
        save_yaml(analysis, analysis_path)

        # Stage 1: Schema validation
        schema_errors = validate_analysis_schema(analysis_path)
        assert schema_errors == [], f"Schema errors: {schema_errors}"

        # Stage 2: Semantic validation
        data = load_yaml(analysis_path)
        semantic_errors = validate_analysis(data)
        assert semantic_errors == [], f"Semantic errors: {semantic_errors}"

        # Stage 3: Evidence verification
        verification_cache = VerificationCache(cache_dir=temp_cache_dir / "verification")
        results = verify_all_insights(data["prior_insights"], paper_cache, verification_cache)

        assert "flexion_insight" in results
        assert results["flexion_insight"].is_valid


class TestRapidFuzzMatching:
    """Tests for RapidFuzz-based fuzzy matching."""

    def test_exact_match(self):
        """Test that exact matches are found."""
        from astra.verification.pdf import PDFDocument

        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=["This is an exact quote from the paper."],
            num_pages=1,
            sha256="test",
        )
        found = pdf.find_quote("This is an exact quote from the paper.")
        assert 1 in found

    def test_case_insensitive_match(self):
        """Test that matching is case-insensitive."""
        from astra.verification.pdf import PDFDocument

        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=["The Model achieves GREAT results."],
            num_pages=1,
            sha256="test",
        )
        found = pdf.find_quote("the model achieves great results")
        assert 1 in found

    def test_fuzzy_match_with_typos(self):
        """Test that fuzzy matching handles minor typos/OCR errors."""
        from astra.verification.pdf import PDFDocument

        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=["The rnodel achieves great resu1ts."],  # OCR errors: rn->m, 1->l
            num_pages=1,
            sha256="test",
        )
        found = pdf.find_quote("The model achieves great results.", min_score=70.0)
        assert 1 in found

    def test_fuzzy_match_with_inline_citations(self):
        """Test that fuzzy matching handles inline citations in PDF text."""
        from astra.verification.pdf import PDFDocument

        # PDF has citations that user's quote doesn't include
        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=["The model [29] achieves great results [1, 2]."],
            num_pages=1,
            sha256="test",
        )
        found = pdf.find_quote("The model achieves great results.", min_score=70.0)
        assert 1 in found

    def test_fuzzy_match_unicode_variations(self):
        """Test that fuzzy matching handles Unicode character variations."""
        from astra.verification.pdf import PDFDocument

        # PDF has different Unicode characters
        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=["The value is ∼100 with α = 0.5"],  # Unicode tilde and alpha
            num_pages=1,
            sha256="test",
        )
        # User might write ASCII approximations
        found = pdf.find_quote("The value is ~100 with alpha = 0.5", min_score=60.0)
        assert 1 in found

    def test_quote_not_found(self):
        """Test that non-existent quotes are not found."""
        from astra.verification.pdf import PDFDocument

        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=["This paper discusses machine learning algorithms for image classification."],
            num_pages=1,
            sha256="test",
        )
        # Completely different content should not match
        found = pdf.find_quote(
            "Quantum entanglement enables faster-than-light communication.",
            min_score=70.0,
        )
        assert len(found) == 0


class TestPrefixSuffixContext:
    """Tests for W3C TextQuoteSelector prefix/suffix disambiguation."""

    def test_prefix_suffix_disambiguation(self):
        """Test that prefix/suffix help disambiguate repeated quotes.

        In practice, prefix/suffix provide unique context like section headers,
        figure references, or distinctive surrounding text.
        """
        from astra.verification.pdf import PDFDocument

        # Same quote appears twice with very different context
        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=[
                "As shown in Figure 3, the neural network achieves high accuracy. "
                "This validates our hypothesis about deep learning.",
                "According to Table 7, the random forest achieves high accuracy. "
                "This confirms the baseline performance.",
            ],
            num_pages=2,
            sha256="test",
        )

        # Without prefix/suffix, both pages match the common phrase
        found = pdf.find_quote("achieves high accuracy")
        assert len(found) == 2

        # With prefix, only page 1 matches (neural network context)
        found = pdf.find_quote(
            "achieves high accuracy",
            prefix="As shown in Figure 3, the neural network",
        )
        assert 1 in found
        assert 2 not in found

    def test_suffix_context(self):
        """Test that suffix helps narrow down matches."""
        from astra.verification.pdf import PDFDocument

        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=[
                "The algorithm converges rapidly. Theorem 4.2 provides the convergence guarantee.",
                "The algorithm converges rapidly. Empirical results support this observation.",
            ],
            num_pages=2,
            sha256="test",
        )

        # With suffix specifying the theorem reference, only page 1 matches
        found = pdf.find_quote(
            "The algorithm converges rapidly.",
            suffix="Theorem 4.2 provides the convergence guarantee.",
        )
        assert 1 in found
        assert 2 not in found


class TestPageHint:
    """Tests for page hint in quote verification."""

    def test_page_hint_optimizes_search(self):
        """Test that page hint is used to optimize search order."""
        from astra.verification.core import VerificationStatus, verify_quote_in_pdf
        from astra.verification.pdf import PDFDocument

        # Create a mock PDF with 10 pages
        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=["" for _ in range(10)],
            num_pages=10,
            sha256="test",
        )
        # Put the quote on page 5 (0-indexed: page 4)
        pdf.pages[4] = "This is the quote we are looking for."

        # Page hint doesn't affect verification - quote found anywhere is VERIFIED
        status, found_pages, message = verify_quote_in_pdf(
            "This is the quote we are looking for",
            pdf,
            page_hint=1,  # Hint is wrong, but quote should still be found
        )
        assert status == VerificationStatus.VERIFIED
        assert 5 in found_pages

    def test_no_page_hint(self):
        """Test verification works without page hint."""
        from astra.verification.core import VerificationStatus, verify_quote_in_pdf
        from astra.verification.pdf import PDFDocument

        pdf = PDFDocument(
            path=None,  # type: ignore
            pages=["" for _ in range(10)],
            num_pages=10,
            sha256="test",
        )
        pdf.pages[4] = "This is the quote we are looking for."

        # No page hint - should still find and verify quote
        status, found_pages, message = verify_quote_in_pdf(
            "This is the quote we are looking for",
            pdf,
            page_hint=None,
        )
        assert status == VerificationStatus.VERIFIED
        assert 5 in found_pages
