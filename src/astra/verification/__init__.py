"""Evidence verification for ASTRA insights.

Provides functionality to verify that evidence (quotes, figures, tables)
actually exists in the referenced source documents.

Requires optional dependencies: pip install astra[verify]
"""

from astra.verification.cache import VerificationCache, VerificationCacheEntry
from astra.verification.core import (
    EvidenceVerification,
    InsightVerification,
    VerificationStatus,
    verify_all_insights,
    verify_evidence,
    verify_insight,
)
from astra.verification.pdf import (
    PDFDocument,
    extract_text_from_pdf,
    normalize_text,
)

__all__ = [
    # Verification
    "EvidenceVerification",
    "InsightVerification",
    "VerificationStatus",
    "verify_evidence",
    "verify_insight",
    "verify_all_insights",
    # Cache
    "VerificationCache",
    "VerificationCacheEntry",
    # PDF utilities
    "PDFDocument",
    "extract_text_from_pdf",
    "normalize_text",
]
