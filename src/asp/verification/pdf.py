"""PDF handling for evidence verification.

Downloads arXiv PDFs and extracts text for quote verification.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Check for optional dependencies
# These are optional and may not be installed
httpx: Any = None
pdftext: Any = None

try:
    import httpx as _httpx  # type: ignore[import-not-found,unused-ignore]

    httpx = _httpx
except ImportError:
    pass

try:
    from pdftext import extraction as pdftext_extraction  # type: ignore[import-not-found]

    pdftext = pdftext_extraction
except ImportError:
    pdftext = None


def _check_dependencies() -> None:
    """Raise ImportError if verification dependencies are missing."""
    missing = []
    if httpx is None:
        missing.append("httpx")
    if pdftext is None:
        missing.append("pdftext")
    if missing:
        raise ImportError(
            f"Missing verification dependencies: {', '.join(missing)}. "
            "Install with: pip install asp[verify]"
        )


@dataclass
class PDFDocument:
    """A PDF document with extracted text by page.

    Attributes:
        path: Path to the PDF file.
        pages: List of text content per page (0-indexed).
        num_pages: Total number of pages.
        sha256: SHA-256 hash of the PDF content.
    """

    path: Path
    pages: list[str] = field(default_factory=list)
    num_pages: int = 0
    sha256: str = ""

    def get_page_text(self, page: int) -> str | None:
        """Get text for a specific page (1-indexed as per FragmentSelector).

        Args:
            page: 1-indexed page number.

        Returns:
            Text content of the page, or None if page is out of range.
        """
        if page < 1 or page > self.num_pages:
            return None
        return self.pages[page - 1]

    def get_full_text(self) -> str:
        """Get concatenated text from all pages."""
        return "\n\n".join(self.pages)

    def find_quote(
        self,
        quote: str,
        page: int | None = None,
        min_match_ratio: float = 0.7,
    ) -> list[int]:
        """Find pages containing a quote.

        Uses fuzzy matching to handle OCR/extraction differences.

        Args:
            quote: The quote to search for.
            page: Optional page hint (1-indexed). If provided, searches this page first.
            min_match_ratio: Minimum similarity ratio for fuzzy matching.

        Returns:
            List of 1-indexed page numbers where quote was found.
        """
        found_pages = []
        normalized_quote = _normalize_text(quote)

        # Search pages (prioritize hint page if provided)
        pages_to_search = list(range(self.num_pages))
        if page is not None and 1 <= page <= self.num_pages:
            # Move hint page to front
            pages_to_search.remove(page - 1)
            pages_to_search.insert(0, page - 1)

        for page_idx in pages_to_search:
            page_text = _normalize_text(self.pages[page_idx])

            # Exact match
            if normalized_quote in page_text:
                found_pages.append(page_idx + 1)
                continue

            # Fuzzy match using simple similarity
            if _fuzzy_contains(page_text, normalized_quote, min_match_ratio):
                found_pages.append(page_idx + 1)

        return found_pages


def _normalize_text(text: str) -> str:
    """Normalize text for comparison.

    Handles common PDF extraction issues:
    - Unicode normalization
    - Whitespace normalization
    - Common character substitutions
    """
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text.strip())

    # Common Unicode -> ASCII substitutions for scientific text
    replacements = {
        "\u2013": "-",  # en-dash
        "\u2014": "--",  # em-dash
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u00b1": "+-",  # plus-minus
        "\u00d7": "x",  # multiplication
        "\u03c3": "sigma",  # sigma
        "\u03b1": "alpha",  # alpha
        "\u03b2": "beta",  # beta
        "\u2264": "<=",  # less than or equal
        "\u2265": ">=",  # greater than or equal
        "\ufb01": "fi",  # fi ligature
        "\ufb02": "fl",  # fl ligature
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    return text.lower()


def _fuzzy_contains(haystack: str, needle: str, min_ratio: float) -> bool:
    """Check if haystack contains needle with fuzzy matching.

    Uses a simple sliding window approach.
    """
    if len(needle) > len(haystack):
        return False

    # Slide a window of needle's length across haystack
    window_size = len(needle)

    for i in range(len(haystack) - window_size + 1):
        window = haystack[i : i + window_size]
        ratio = _similarity_ratio(window, needle)
        if ratio >= min_ratio:
            return True

    return False


def _similarity_ratio(s1: str, s2: str) -> float:
    """Calculate similarity ratio between two strings."""
    if not s1 or not s2:
        return 0.0

    # Simple character-based similarity
    matches = sum(1 for a, b in zip(s1, s2) if a == b)
    return matches / max(len(s1), len(s2))


def get_arxiv_pdf(
    source: Any,
    cache_dir: Path | None = None,
) -> Path:
    """Download an arXiv PDF.

    Args:
        source: ArxivSource dict or object with arxiv_id and version.
        cache_dir: Directory to cache PDFs. Defaults to ~/.cache/asp/pdfs.

    Returns:
        Path to the downloaded PDF.

    Raises:
        ImportError: If httpx is not installed.
        httpx.HTTPError: If download fails.
    """
    _check_dependencies()

    # Handle both dict and object
    if isinstance(source, dict):
        arxiv_id = source["arxiv_id"]
        version = source["version"]
    else:
        arxiv_id = source.arxiv_id
        version = source.version

    # Set up cache directory
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "asp" / "pdfs"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Check cache
    filename = f"{arxiv_id.replace('/', '_')}v{version}.pdf"
    cached_path = cache_dir / filename

    if cached_path.exists():
        return cached_path

    # Download
    url = f"https://arxiv.org/pdf/{arxiv_id}v{version}.pdf"
    response = httpx.get(url, follow_redirects=True, timeout=60.0)
    response.raise_for_status()

    # Save to cache
    cached_path.write_bytes(response.content)

    return cached_path


def extract_text_from_pdf(pdf_path: Path) -> PDFDocument:
    """Extract text from a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        PDFDocument with extracted text and metadata.

    Raises:
        ImportError: If pdftext is not installed.
    """
    _check_dependencies()

    # Calculate SHA-256
    sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    # Extract text by page
    pages = pdftext.paginated_plain_text_output(str(pdf_path), sort=True, hyphens=False)

    return PDFDocument(
        path=pdf_path,
        pages=pages,
        num_pages=len(pages),
        sha256=sha256,
    )
