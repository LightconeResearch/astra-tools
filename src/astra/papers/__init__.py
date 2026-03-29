"""Paper management for ASTRA.

Provides DOI-based paper acquisition and caching for evidence verification.
"""

from astra.papers.cache import PaperCache, PaperMetadata
from astra.papers.download import download_paper, is_valid_pdf, resolve_doi

__all__ = [
    "PaperCache",
    "PaperMetadata",
    "download_paper",
    "is_valid_pdf",
    "resolve_doi",
]
