"""Evidence verification cache for ASTRA.

Caches verification results to avoid re-verifying unchanged evidence.

Cache structure:
    ~/.cache/astra/verification/
    └── evidence.json  # {cache_key: {verified_at, pdf_sha256, status}}

Cache key: (doi, version, sha256(quote.exact))
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _compute_quote_hash(quote_exact: str) -> str:
    """Compute SHA-256 hash of quote text."""
    return hashlib.sha256(quote_exact.encode("utf-8")).hexdigest()


def _make_cache_key(doi: str, version: int | None, quote_hash: str) -> str:
    """Create a cache key for an evidence verification result."""
    version_str = str(version) if version is not None else "latest"
    return f"{doi}|{version_str}|{quote_hash}"


@dataclass
class VerificationCacheEntry:
    """A cached evidence verification result.

    Attributes:
        doi: DOI of the source paper.
        version: Paper version (for arXiv).
        quote_hash: SHA-256 of the quote text.
        pdf_sha256: SHA-256 of the PDF used for verification.
        status: Verification status ('verified', 'not_found', 'wrong_page').
        found_pages: Pages where quote was found (1-indexed).
        expected_page: Expected page from location hint.
        verified_at: When verification was performed.
    """

    doi: str
    version: int | None
    quote_hash: str
    pdf_sha256: str
    status: str
    verified_at: str
    found_pages: list[int] | None = None
    expected_page: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationCacheEntry:
        """Create from dict."""
        return cls(
            doi=data["doi"],
            version=data.get("version"),
            quote_hash=data["quote_hash"],
            pdf_sha256=data["pdf_sha256"],
            status=data["status"],
            verified_at=data["verified_at"],
            found_pages=data.get("found_pages"),
            expected_page=data.get("expected_page"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        result = asdict(self)
        # Remove None values for cleaner JSON
        return {k: v for k, v in result.items() if v is not None}

    @property
    def cache_key(self) -> str:
        """Get the cache key for this entry."""
        return _make_cache_key(self.doi, self.version, self.quote_hash)


class VerificationCache:
    """Cache for evidence verification results.

    Stores verification results keyed by (DOI, version, quote_hash).
    Cache is invalidated if PDF SHA-256 changes.
    """

    def __init__(self, cache_dir: Path | None = None):
        """Initialize the verification cache.

        Args:
            cache_dir: Directory for cache. Defaults to ~/.cache/astra/verification.
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "astra" / "verification"
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / "evidence.json"
        self._cache: dict[str, VerificationCacheEntry] | None = None

    def _load_cache(self) -> dict[str, VerificationCacheEntry]:
        """Load cache from disk."""
        if self._cache is not None:
            return self._cache

        self._cache = {}
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    data = json.load(f)
                for key, entry_data in data.items():
                    self._cache[key] = VerificationCacheEntry.from_dict(entry_data)
            except (json.JSONDecodeError, KeyError):
                self._cache = {}

        return self._cache

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if self._cache is None:
            return

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        data = {key: entry.to_dict() for key, entry in self._cache.items()}
        with open(self.cache_file, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def get(
        self,
        doi: str,
        version: int | None,
        quote_exact: str,
        pdf_sha256: str,
    ) -> VerificationCacheEntry | None:
        """Get a cached verification result.

        Args:
            doi: DOI of the paper.
            version: Paper version (for arXiv).
            quote_exact: Exact quote text.
            pdf_sha256: SHA-256 of the current PDF.

        Returns:
            VerificationCacheEntry if cached and PDF unchanged, None otherwise.
        """
        cache = self._load_cache()
        quote_hash = _compute_quote_hash(quote_exact)
        key = _make_cache_key(doi, version, quote_hash)

        entry = cache.get(key)
        if entry is None:
            return None

        # Invalidate if PDF changed
        if entry.pdf_sha256 != pdf_sha256:
            return None

        return entry

    def set(
        self,
        doi: str,
        version: int | None,
        quote_exact: str,
        pdf_sha256: str,
        status: str,
        found_pages: list[int] | None = None,
        expected_page: int | None = None,
    ) -> VerificationCacheEntry:
        """Cache a verification result.

        Args:
            doi: DOI of the paper.
            version: Paper version (for arXiv).
            quote_exact: Exact quote text.
            pdf_sha256: SHA-256 of the PDF used.
            status: Verification status.
            found_pages: Pages where quote was found.
            expected_page: Expected page from location hint.

        Returns:
            The cached entry.
        """
        cache = self._load_cache()
        quote_hash = _compute_quote_hash(quote_exact)

        entry = VerificationCacheEntry(
            doi=doi,
            version=version,
            quote_hash=quote_hash,
            pdf_sha256=pdf_sha256,
            status=status,
            verified_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            found_pages=found_pages,
            expected_page=expected_page,
        )

        cache[entry.cache_key] = entry
        self._save_cache()

        return entry

    def invalidate(self, doi: str, version: int | None = None) -> int:
        """Invalidate all cached entries for a DOI.

        Args:
            doi: DOI to invalidate.
            version: If provided, only invalidate entries for this version.

        Returns:
            Number of entries invalidated.
        """
        cache = self._load_cache()
        keys_to_remove = [
            key
            for key, entry in cache.items()
            if entry.doi == doi and (version is None or entry.version == version)
        ]

        for key in keys_to_remove:
            del cache[key]

        if keys_to_remove:
            self._save_cache()

        return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()
