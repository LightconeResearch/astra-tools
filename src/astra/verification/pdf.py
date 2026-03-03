"""PDF handling for evidence verification.

Extracts text from PDFs for quote verification using RapidFuzz for robust matching.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

# Greek letter mappings for normalization
# Maps Greek letters to ASCII equivalents for fuzzy matching
GREEK_TO_ASCII: dict[str, str] = {
    # Lowercase Greek
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "ζ": "zeta",
    "η": "eta",
    "θ": "theta",
    "ι": "iota",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "ξ": "xi",
    "ο": "omicron",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "ς": "sigma",  # Final sigma
    "τ": "tau",
    "υ": "upsilon",
    "φ": "phi",
    "χ": "chi",
    "ψ": "psi",
    "ω": "omega",
    # Uppercase Greek
    "Α": "Alpha",
    "Β": "Beta",
    "Γ": "Gamma",
    "Δ": "Delta",
    "Ε": "Epsilon",
    "Ζ": "Zeta",
    "Η": "Eta",
    "Θ": "Theta",
    "Ι": "Iota",
    "Κ": "Kappa",
    "Λ": "Lambda",
    "Μ": "Mu",
    "Ν": "Nu",
    "Ξ": "Xi",
    "Ο": "Omicron",
    "Π": "Pi",
    "Ρ": "Rho",
    "Σ": "Sigma",
    "Τ": "Tau",
    "Υ": "Upsilon",
    "Φ": "Phi",
    "Χ": "Chi",
    "Ψ": "Psi",
    "Ω": "Omega",
}

# Math symbol normalizations
MATH_SYMBOL_MAP: dict[str, str] = {
    "≈": "~",
    "∼": "~",
    "≃": "~",
    "≅": "~",
    "≡": "=",
    "≠": "!=",
    "≤": "<=",
    "≥": ">=",
    "±": "+-",
    "∓": "-+",
    "×": "x",
    "÷": "/",
    "−": "-",  # Unicode minus to ASCII hyphen-minus
    "–": "-",  # En dash to hyphen
    "—": "-",  # Em dash to hyphen
    "′": "'",  # Prime to apostrophe
    "″": "''",  # Double prime
    "∞": "inf",
}

# Subscript/superscript to regular characters
SUBSCRIPT_MAP: dict[str, str] = {
    "₀": "0",
    "₁": "1",
    "₂": "2",
    "₃": "3",
    "₄": "4",
    "₅": "5",
    "₆": "6",
    "₇": "7",
    "₈": "8",
    "₉": "9",
    "₊": "+",
    "₋": "-",
    "₌": "=",
    "₍": "(",
    "₎": ")",
    "ₐ": "a",
    "ₑ": "e",
    "ₕ": "h",
    "ᵢ": "i",
    "ⱼ": "j",
    "ₖ": "k",
    "ₗ": "l",
    "ₘ": "m",
    "ₙ": "n",
    "ₒ": "o",
    "ₚ": "p",
    "ᵣ": "r",
    "ₛ": "s",
    "ₜ": "t",
    "ᵤ": "u",
    "ᵥ": "v",
    "ₓ": "x",
}

SUPERSCRIPT_MAP: dict[str, str] = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁺": "+",
    "⁻": "-",
    "⁼": "=",
    "⁽": "(",
    "⁾": ")",
    "ⁿ": "n",
    "ⁱ": "i",
}


def normalize_text(text: str) -> str:
    """Normalize text for robust fuzzy matching.

    Applies:
    1. NFKC Unicode normalization (handles ligatures, compatibility chars)
    2. Greek letter to ASCII conversion
    3. Math symbol normalization
    4. Subscript/superscript normalization
    5. Whitespace normalization

    Args:
        text: Input text to normalize.

    Returns:
        Normalized text suitable for fuzzy matching.
    """
    if not text:
        return ""

    # Step 1: NFKC normalization (converts ﬁ→fi, decomposes compatibility chars)
    result = unicodedata.normalize("NFKC", text)

    # Step 2: Replace Greek letters with ASCII equivalents
    for greek, ascii_equiv in GREEK_TO_ASCII.items():
        result = result.replace(greek, ascii_equiv)

    # Step 3: Replace math symbols
    for symbol, replacement in MATH_SYMBOL_MAP.items():
        result = result.replace(symbol, replacement)

    # Step 4: Replace subscripts and superscripts
    for sub, regular in SUBSCRIPT_MAP.items():
        result = result.replace(sub, regular)
    for sup, regular in SUPERSCRIPT_MAP.items():
        result = result.replace(sup, regular)

    # Step 5: Normalize whitespace (collapse multiple spaces, tabs, newlines)
    result = re.sub(r"\s+", " ", result)

    # Step 6: Strip leading/trailing whitespace
    result = result.strip()

    return result


def _normalize_processor(text: str) -> str:
    """Custom processor for rapidfuzz that applies full normalization.

    This combines normalize_text with default_process behavior (lowercasing).
    """
    normalized = normalize_text(text)
    # Apply default_process for lowercasing and additional stripping
    return default_process(normalized)


# pypdf is an optional dependency
PdfReader: Any = None

try:
    from pypdf import PdfReader as _PdfReader

    PdfReader = _PdfReader
except ImportError:
    pass


def _check_pypdf() -> None:
    """Raise ImportError if pypdf is not installed."""
    if PdfReader is None:
        raise ImportError("pypdf is required for PDF extraction. Install with: pip install pypdf")


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
        min_score: float = 70.0,
        prefix: str | None = None,
        suffix: str | None = None,
    ) -> list[int]:
        """Find pages containing a quote using fuzzy matching.

        Uses RapidFuzz's partial_ratio for robust matching that handles:
        - OCR errors and character variations
        - Unicode normalization issues
        - Minor text differences

        Args:
            quote: The quote to search for.
            page: Optional page hint (1-indexed). If provided, searches this page first.
            min_score: Minimum similarity score (0-100) for fuzzy matching.
            prefix: Optional text that should appear before the quote (for disambiguation).
            suffix: Optional text that should appear after the quote (for disambiguation).

        Returns:
            List of 1-indexed page numbers where quote was found.
        """
        found_pages = []

        # Search pages (prioritize hint page if provided)
        pages_to_search = list(range(self.num_pages))
        if page is not None and 1 <= page <= self.num_pages:
            # Move hint page to front
            pages_to_search.remove(page - 1)
            pages_to_search.insert(0, page - 1)

        for page_idx in pages_to_search:
            page_text = self.pages[page_idx]

            # Use partial_ratio which finds the best matching substring
            # _normalize_processor handles Greek letters, math symbols, and lowercasing
            score = fuzz.partial_ratio(quote, page_text, processor=_normalize_processor)

            if score >= min_score:
                # If prefix/suffix provided, verify context matches too
                if prefix or suffix:
                    if not self._verify_context(page_text, quote, prefix, suffix):
                        continue
                found_pages.append(page_idx + 1)

        return found_pages

    def _verify_context(
        self,
        page_text: str,
        quote: str,
        prefix: str | None,
        suffix: str | None,
    ) -> bool:
        """Verify that prefix/suffix context matches around the quote.

        Uses fuzzy matching to find if the context appears in the expected order.
        The full context (prefix + quote + suffix) must appear as a sequence.
        """
        # Build a context pattern: prefix + quote + suffix
        context_parts = []
        if prefix:
            context_parts.append(prefix.strip())
        context_parts.append(quote.strip())
        if suffix:
            context_parts.append(suffix.strip())

        # Join with flexible whitespace matching
        context = " ".join(context_parts)

        # Check if this context appears in the page with high confidence
        # Use a higher threshold since we want the full context to match
        # _normalize_processor handles Greek letters, math symbols, and lowercasing
        score = fuzz.partial_ratio(context, page_text, processor=_normalize_processor)
        return score >= 80.0


def extract_text_from_pdf(pdf_path: Path) -> PDFDocument:
    """Extract text from a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        PDFDocument with extracted text and metadata.

    Raises:
        ImportError: If pypdf is not installed.
    """
    _check_pypdf()

    # Read PDF content for SHA-256
    pdf_bytes = pdf_path.read_bytes()
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    # Extract text by page using pypdf
    reader = PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]

    return PDFDocument(
        path=pdf_path,
        pages=pages,
        num_pages=len(pages),
        sha256=sha256,
    )
