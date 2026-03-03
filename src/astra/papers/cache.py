"""Paper cache management for ASTRA.

Papers are cached by DOI with optional version for arXiv papers.

Cache structure:
    ~/.cache/astra/papers/
    ├── 10.48550_arXiv.1706.03762_v7/
    │   ├── paper.pdf
    │   └── meta.json
    └── 10.1038_s41586-023-06221-2/
        ├── paper.pdf
        └── meta.json
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sanitize_doi(doi: str, version: int | None = None) -> str:
    """Convert DOI to a safe directory name.

    Args:
        doi: DOI string (e.g., '10.48550/arXiv.1706.03762')
        version: Optional version for arXiv papers

    Returns:
        Safe directory name (e.g., '10.48550_arXiv.1706.03762_v7')
    """
    # Replace path-unsafe characters
    safe = doi.replace("/", "_").replace(":", "_")
    # Remove any other potentially problematic characters
    safe = re.sub(r"[^\w\.\-]", "_", safe)
    if version is not None:
        safe = f"{safe}_v{version}"
    return safe


@dataclass
class PaperMetadata:
    """Metadata for a cached paper.

    Attributes:
        doi: DOI of the paper.
        version: Paper version (for arXiv).
        sha256: SHA-256 hash of the PDF.
        title: Paper title (if known).
        authors: List of authors (if known).
        retrieved_at: When the PDF was retrieved.
        source_url: URL from which PDF was downloaded.
    """

    doi: str
    sha256: str
    retrieved_at: str
    version: int | None = None
    title: str | None = None
    authors: list[str] | None = None
    source_url: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PaperMetadata:
        """Create from JSON dict."""
        return cls(
            doi=data["doi"],
            sha256=data["sha256"],
            retrieved_at=data["retrieved_at"],
            version=data.get("version"),
            title=data.get("title"),
            authors=data.get("authors"),
            source_url=data.get("source_url"),
        )

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON dict."""
        result = asdict(self)
        # Remove None values for cleaner JSON
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class CachedPaper:
    """A paper in the cache with its metadata.

    Attributes:
        pdf_path: Path to the PDF file.
        metadata: Paper metadata.
    """

    pdf_path: Path
    metadata: PaperMetadata


class PaperCache:
    """Cache for downloaded papers.

    Papers are stored by DOI with optional version. Each paper has:
    - paper.pdf: The PDF file
    - meta.json: Metadata including SHA-256, retrieval time, etc.
    """

    def __init__(self, cache_dir: Path | None = None):
        """Initialize the paper cache.

        Args:
            cache_dir: Directory for paper cache. Defaults to ~/.cache/astra/papers.
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "astra" / "papers"
        self.cache_dir = cache_dir

    def _paper_dir(self, doi: str, version: int | None = None) -> Path:
        """Get the cache directory for a paper."""
        return self.cache_dir / _sanitize_doi(doi, version)

    def has(self, doi: str, version: int | None = None) -> bool:
        """Check if a paper is in the cache.

        Args:
            doi: DOI of the paper.
            version: Paper version (for arXiv).

        Returns:
            True if paper is cached with valid PDF and metadata.
        """
        paper_dir = self._paper_dir(doi, version)
        pdf_path = paper_dir / "paper.pdf"
        meta_path = paper_dir / "meta.json"
        return pdf_path.exists() and meta_path.exists()

    def get(self, doi: str, version: int | None = None) -> CachedPaper | None:
        """Get a cached paper.

        Args:
            doi: DOI of the paper.
            version: Paper version (for arXiv).

        Returns:
            CachedPaper if found, None otherwise.
        """
        paper_dir = self._paper_dir(doi, version)
        pdf_path = paper_dir / "paper.pdf"
        meta_path = paper_dir / "meta.json"

        if not (pdf_path.exists() and meta_path.exists()):
            return None

        try:
            with open(meta_path) as f:
                meta_data = json.load(f)
            metadata = PaperMetadata.from_json(meta_data)
            return CachedPaper(pdf_path=pdf_path, metadata=metadata)
        except (json.JSONDecodeError, KeyError):
            return None

    def add(
        self,
        doi: str,
        pdf_content: bytes,
        version: int | None = None,
        title: str | None = None,
        authors: list[str] | None = None,
        source_url: str | None = None,
    ) -> CachedPaper:
        """Add a paper to the cache.

        Args:
            doi: DOI of the paper.
            pdf_content: PDF file content as bytes.
            version: Paper version (for arXiv).
            title: Paper title.
            authors: List of authors.
            source_url: URL from which PDF was downloaded.

        Returns:
            CachedPaper with paths and metadata.
        """
        paper_dir = self._paper_dir(doi, version)
        paper_dir.mkdir(parents=True, exist_ok=True)

        # Write PDF
        pdf_path = paper_dir / "paper.pdf"
        pdf_path.write_bytes(pdf_content)

        # Calculate SHA-256
        sha256 = hashlib.sha256(pdf_content).hexdigest()

        # Create metadata
        metadata = PaperMetadata(
            doi=doi,
            version=version,
            sha256=sha256,
            title=title,
            authors=authors,
            source_url=source_url,
            retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

        # Write metadata
        meta_path = paper_dir / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(metadata.to_json(), f, indent=2)
            f.write("\n")

        return CachedPaper(pdf_path=pdf_path, metadata=metadata)

    def add_from_file(
        self,
        doi: str,
        pdf_path: Path,
        version: int | None = None,
        title: str | None = None,
        authors: list[str] | None = None,
    ) -> CachedPaper:
        """Add a paper to the cache from a local file.

        Args:
            doi: DOI of the paper.
            pdf_path: Path to the PDF file.
            version: Paper version (for arXiv).
            title: Paper title.
            authors: List of authors.

        Returns:
            CachedPaper with paths and metadata.
        """
        pdf_content = pdf_path.read_bytes()
        return self.add(
            doi=doi,
            pdf_content=pdf_content,
            version=version,
            title=title,
            authors=authors,
            source_url=f"file://{pdf_path.absolute()}",
        )

    def remove(self, doi: str, version: int | None = None) -> bool:
        """Remove a paper from the cache.

        Args:
            doi: DOI of the paper.
            version: Paper version (for arXiv).

        Returns:
            True if paper was removed, False if not found.
        """
        paper_dir = self._paper_dir(doi, version)
        if paper_dir.exists():
            shutil.rmtree(paper_dir)
            return True
        return False

    def list_papers(self) -> list[CachedPaper]:
        """List all cached papers.

        Returns:
            List of CachedPaper objects.
        """
        papers: list[CachedPaper] = []
        if not self.cache_dir.exists():
            return papers

        for paper_dir in self.cache_dir.iterdir():
            if not paper_dir.is_dir():
                continue
            pdf_path = paper_dir / "paper.pdf"
            meta_path = paper_dir / "meta.json"
            if pdf_path.exists() and meta_path.exists():
                try:
                    with open(meta_path) as f:
                        meta_data = json.load(f)
                    metadata = PaperMetadata.from_json(meta_data)
                    papers.append(CachedPaper(pdf_path=pdf_path, metadata=metadata))
                except (json.JSONDecodeError, KeyError):
                    continue

        return papers

    def get_path(self, doi: str, version: int | None = None) -> Path | None:
        """Get the PDF path for a cached paper.

        Args:
            doi: DOI of the paper.
            version: Paper version (for arXiv).

        Returns:
            Path to the PDF if cached, None otherwise.
        """
        paper = self.get(doi, version)
        if paper:
            return paper.pdf_path
        return None

    def update_metadata(
        self,
        doi: str,
        version: int | None = None,
        title: str | None = None,
        authors: list[str] | None = None,
    ) -> bool:
        """Update metadata for a cached paper.

        Useful for adding title/authors to papers that were cached without metadata.

        Args:
            doi: DOI of the paper.
            version: Paper version (for arXiv).
            title: Paper title to set.
            authors: List of authors to set.

        Returns:
            True if metadata was updated, False if paper not found.
        """
        paper = self.get(doi, version)
        if not paper:
            return False

        # Update metadata
        if title is not None:
            paper.metadata.title = title
        if authors is not None:
            paper.metadata.authors = authors

        # Write updated metadata
        paper_dir = self._paper_dir(doi, version)
        meta_path = paper_dir / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(paper.metadata.to_json(), f, indent=2)
            f.write("\n")

        return True
