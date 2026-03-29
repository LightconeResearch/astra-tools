"""DOI resolution and paper downloading for ASTRA.

Downloads papers by DOI, with special handling for arXiv papers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Optional dependency for HTTP requests
httpx: Any = None

try:
    import httpx as _httpx  # type: ignore[import-not-found,unused-ignore]

    httpx = _httpx
except ImportError:
    pass


def _check_httpx() -> None:
    """Raise ImportError if httpx is not installed."""
    if httpx is None:
        raise ImportError(
            "httpx is required for paper downloading. Install with: pip install astra[verify]"
        )


@dataclass
class DOIMetadata:
    """Metadata retrieved from DOI content negotiation.

    Attributes:
        title: Paper title.
        authors: List of author names.
        doi: The DOI.
        published: Publication date (if available).
        container_title: Journal/conference name (if available).
    """

    title: str | None = None
    authors: list[str] | None = None
    doi: str | None = None
    published: str | None = None
    container_title: str | None = None


def fetch_doi_metadata(doi: str) -> DOIMetadata:
    """Fetch metadata for any DOI using content negotiation.

    Uses the DOI.org content negotiation to retrieve CSL-JSON metadata.
    This works for any DOI registration agency (Crossref, DataCite, arXiv, etc.).

    See: https://citation.doi.org/docs.html

    Args:
        doi: DOI string (e.g., '10.1038/nature12373').

    Returns:
        DOIMetadata with title, authors, etc. Fields may be None if not available.
    """
    _check_httpx()

    url = f"https://doi.org/{doi}"
    headers = {"Accept": "application/vnd.citationstyles.csl+json"}

    try:
        response = httpx.get(url, headers=headers, follow_redirects=True, timeout=30.0)
        response.raise_for_status()

        data = response.json()

        # Extract title
        title = data.get("title")

        # Extract authors - CSL-JSON uses "author" array with "family" and "given"
        authors = None
        if data.get("author"):
            authors = []
            for author in data["author"]:
                if author.get("family"):
                    name = author.get("given", "")
                    if name:
                        name += " "
                    name += author["family"]
                    authors.append(name.strip())
                elif author.get("literal"):
                    # Some entries use "literal" for organization names
                    authors.append(author["literal"])

        # Extract publication date
        published = None
        if data.get("issued") and data["issued"].get("date-parts"):
            date_parts = data["issued"]["date-parts"][0]
            if date_parts:
                published = "-".join(str(p) for p in date_parts if p)

        # Extract container title (journal/conference)
        container_title = data.get("container-title")

        return DOIMetadata(
            title=title,
            authors=authors,
            doi=data.get("DOI", doi),
            published=published,
            container_title=container_title,
        )

    except (httpx.HTTPStatusError, httpx.RequestError):
        # Return empty metadata on error - don't fail the download
        return DOIMetadata()
    except (KeyError, ValueError):
        # JSON parsing issues
        return DOIMetadata()


@dataclass
class PaperDownloadResult:
    """Result of a paper download attempt.

    Attributes:
        success: Whether download succeeded.
        content: PDF bytes if successful.
        url: URL from which PDF was downloaded.
        title: Paper title if available.
        authors: List of authors if available.
        error: Error message if failed.
    """

    success: bool
    content: bytes | None = None
    url: str | None = None
    title: str | None = None
    authors: list[str] | None = None
    error: str | None = None


def is_valid_pdf(content: bytes) -> bool:
    """Check if content is a valid PDF by inspecting magic bytes.

    Args:
        content: Raw bytes of the downloaded file.

    Returns:
        True if the content starts with the PDF magic bytes ``%PDF``.
    """
    return content[:4] == b"%PDF"


def _is_arxiv_doi(doi: str) -> bool:
    """Check if DOI is an arXiv DOI."""
    return doi.startswith("10.48550/arXiv.")


def _extract_arxiv_id(doi: str) -> str | None:
    """Extract arXiv ID from arXiv DOI."""
    if _is_arxiv_doi(doi):
        return doi.replace("10.48550/arXiv.", "")
    return None


def _download_arxiv_pdf(arxiv_id: str, doi: str, version: int | None = None) -> PaperDownloadResult:
    """Download PDF from arXiv.

    Args:
        arxiv_id: arXiv ID (e.g., '1706.03762').
        doi: Full DOI for the paper (used for metadata lookup).
        version: Paper version. If None, downloads latest.

    Returns:
        PaperDownloadResult with PDF content or error.
    """
    _check_httpx()

    # Construct URL
    if version is not None:
        url = f"https://arxiv.org/pdf/{arxiv_id}v{version}.pdf"
    else:
        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    try:
        response = httpx.get(url, follow_redirects=True, timeout=60.0)
        response.raise_for_status()

        # Check if we got a PDF (arXiv returns application/pdf or application/octet-stream)
        content_type = response.headers.get("content-type", "")
        is_pdf_content_type = "application/pdf" in content_type or content_type.startswith(
            "application/octet"
        )
        if not is_pdf_content_type:
            return PaperDownloadResult(
                success=False, error=f"Unexpected content type: {content_type}"
            )

        # Validate magic bytes — guard against content-type lies
        if not is_valid_pdf(response.content):
            return PaperDownloadResult(
                success=False,
                error="Downloaded content is not a valid PDF (magic bytes mismatch)",
            )

        # Fetch metadata using DOI content negotiation
        metadata = fetch_doi_metadata(doi)

        return PaperDownloadResult(
            success=True,
            content=response.content,
            url=url,
            title=metadata.title,
            authors=metadata.authors,
        )

    except httpx.HTTPStatusError as e:
        return PaperDownloadResult(
            success=False,
            error=f"HTTP error {e.response.status_code}: {e.response.reason_phrase}",
        )
    except httpx.RequestError as e:
        return PaperDownloadResult(
            success=False,
            error=f"Request error: {e}",
        )


def _try_unpaywall(doi: str) -> PaperDownloadResult:
    """Try to get open access PDF URL via Unpaywall.

    Args:
        doi: DOI of the paper.

    Returns:
        PaperDownloadResult with PDF content or error.
    """
    _check_httpx()

    # Unpaywall requires an email for polite use
    # Using a generic ASTRA email - users should configure their own
    email = "astra-tool@example.org"
    url = f"https://api.unpaywall.org/v2/{doi}?email={email}"

    try:
        response = httpx.get(url, timeout=30.0)
        if response.status_code == 404:
            return PaperDownloadResult(
                success=False,
                error="DOI not found in Unpaywall",
            )
        response.raise_for_status()

        data = response.json()

        # Try to find best open access location
        best_oa = data.get("best_oa_location")
        if not best_oa:
            return PaperDownloadResult(
                success=False,
                error="No open access version available",
            )

        pdf_url = best_oa.get("url_for_pdf")
        if not pdf_url:
            # Try the regular URL
            pdf_url = best_oa.get("url")

        if not pdf_url:
            return PaperDownloadResult(
                success=False,
                error="No PDF URL available",
            )

        # Download the PDF
        pdf_response = httpx.get(pdf_url, follow_redirects=True, timeout=60.0)
        pdf_response.raise_for_status()

        # Validate that we actually got a PDF and not an HTML redirect/paywall page
        if not is_valid_pdf(pdf_response.content):
            content_type = pdf_response.headers.get("content-type", "unknown")
            return PaperDownloadResult(
                success=False,
                error=(
                    f"Downloaded content is not a valid PDF (got content-type: {content_type}). "
                    "The URL may have redirected to a paywall or CAPTCHA page."
                ),
            )

        # Extract metadata
        title = data.get("title")
        authors = None
        if data.get("z_authors"):
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in data["z_authors"]
                if a.get("family")
            ]

        return PaperDownloadResult(
            success=True,
            content=pdf_response.content,
            url=pdf_url,
            title=title,
            authors=authors,
        )

    except httpx.HTTPStatusError as e:
        return PaperDownloadResult(
            success=False,
            error=f"Unpaywall HTTP error: {e.response.status_code}",
        )
    except httpx.RequestError as e:
        return PaperDownloadResult(
            success=False,
            error=f"Unpaywall request error: {e}",
        )


def resolve_doi(doi: str) -> str:
    """Resolve a DOI to its target URL.

    Args:
        doi: DOI to resolve.

    Returns:
        Target URL.
    """
    _check_httpx()

    url = f"https://doi.org/{doi}"
    response = httpx.head(url, follow_redirects=True, timeout=30.0)
    return str(response.url)


def download_paper(doi: str, version: int | None = None) -> PaperDownloadResult:
    """Download a paper by DOI.

    For arXiv papers (DOI starting with 10.48550/arXiv.), downloads directly
    from arXiv. For other papers, tries Unpaywall for open access versions.

    Metadata (title, authors) is fetched automatically via DOI content negotiation.

    Args:
        doi: DOI of the paper.
        version: Paper version (only used for arXiv papers).

    Returns:
        PaperDownloadResult with PDF content or error.
    """
    # Handle arXiv papers specially
    arxiv_id = _extract_arxiv_id(doi)
    if arxiv_id:
        return _download_arxiv_pdf(arxiv_id, doi, version)

    # For non-arXiv papers, try Unpaywall
    return _try_unpaywall(doi)


def download_paper_to_cache(
    doi: str,
    cache_dir: Path | None = None,
    version: int | None = None,
) -> tuple[Path, PaperDownloadResult]:
    """Download a paper and save to cache.

    This is a convenience function that combines downloading and caching.

    Args:
        doi: DOI of the paper.
        cache_dir: Cache directory. Defaults to ~/.cache/astra/papers.
        version: Paper version (for arXiv).

    Returns:
        Tuple of (PDF path, download result).
    """
    from astra.papers.cache import PaperCache

    cache = PaperCache(cache_dir)

    # Check if already cached
    existing = cache.get(doi, version)
    if existing:
        return existing.pdf_path, PaperDownloadResult(
            success=True,
            url=existing.metadata.source_url,
            title=existing.metadata.title,
            authors=existing.metadata.authors,
        )

    # Download
    result = download_paper(doi, version)
    if not result.success or result.content is None:
        return Path(), result

    # Cache
    paper = cache.add(
        doi=doi,
        pdf_content=result.content,
        version=version,
        title=result.title,
        authors=result.authors,
        source_url=result.url,
    )

    return paper.pdf_path, result
