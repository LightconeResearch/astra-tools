"""`astra paper add|list|show|path|remove|fetch-metadata|verify-quotes|verify-quote`: the
papers that evidence cites by DOI, kept in the paper cache, and quotes sought in them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


@click.group("paper")
def command() -> None:
    """Paper management commands for evidence verification."""
    pass


@command.command("add")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
@click.option(
    "--pdf",
    type=click.Path(exists=True, path_type=Path),
    help="Use local PDF instead of downloading",
)
def paper_add(doi: str, version: int | None, pdf: Path | None) -> None:
    """Add a paper to the cache by DOI.

    DOI can be any valid DOI. For arXiv papers, use the format:
    10.48550/arXiv.1706.03762

    Examples:
        astra paper add 10.48550/arXiv.1706.03762 --version 7
        astra paper add 10.1038/s41586-023-06221-2
        astra paper add 10.1234/example --pdf ./local_paper.pdf
    """
    from astra.cli.text import console as _console

    console = _console()
    from astra.papers.cache import PaperCache
    from astra.papers.download import download_paper

    cache = PaperCache()

    # Check if already cached
    if cache.has(doi, version):
        paper = cache.get(doi, version)
        if paper:
            console.print(f"[yellow]Paper already cached:[/yellow] {doi}")
            console.print(f"  Path: {paper.pdf_path}")
            if paper.metadata.title:
                console.print(f"  Title: {paper.metadata.title}")
            return

    # Add from local file or download
    if pdf:
        console.print(f"Adding paper from local file: [cyan]{pdf}[/cyan]")
        paper = cache.add_from_file(doi, pdf, version=version)
        console.print("[green]✓[/green] Paper added to cache")
        console.print(f"  DOI: {doi}")
        if version:
            console.print(f"  Version: {version}")
        console.print(f"  Path: {paper.pdf_path}")
        console.print(f"  SHA-256: {paper.metadata.sha256[:16]}...")
    else:
        console.print(f"Downloading paper: [cyan]{doi}[/cyan]")
        if version:
            console.print(f"  Version: {version}")

        result = download_paper(doi, version)

        if not result.success:
            console.print(f"[red]Error:[/red] {result.error}")
            raise SystemExit(1)

        if result.content is None:
            console.print("[red]Error:[/red] No content received")
            raise SystemExit(1)

        paper = cache.add(
            doi=doi,
            pdf_content=result.content,
            version=version,
            title=result.title,
            authors=result.authors,
            source_url=result.url,
        )

        console.print("[green]✓[/green] Paper downloaded and cached")
        console.print(f"  DOI: {doi}")
        if version:
            console.print(f"  Version: {version}")
        if paper.metadata.title:
            console.print(f"  Title: {paper.metadata.title}")
        console.print(f"  Path: {paper.pdf_path}")
        console.print(f"  SHA-256: {paper.metadata.sha256[:16]}...")


@command.command("list")
def paper_list() -> None:
    """List all cached papers."""
    from astra.cli.text import Table
    from astra.cli.text import console as _console

    console = _console()
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    papers = cache.list_papers()

    if not papers:
        console.print("[dim]No papers cached[/dim]")
        return

    table = Table(show_header=True, expand=True)
    table.add_column("DOI", no_wrap=True)
    table.add_column("Ver", no_wrap=True)
    table.add_column("Title", ratio=2)
    table.add_column("Retrieved", no_wrap=True)

    for paper in papers:
        meta = paper.metadata
        version_str = str(meta.version) if meta.version else "-"
        title = meta.title or "[dim](unknown)[/dim]"
        retrieved = meta.retrieved_at[:10] if meta.retrieved_at else "-"
        table.add_row(meta.doi, version_str, title, retrieved)

    console.print(table)
    console.print(f"\n[dim]{len(papers)} paper(s) cached[/dim]")


@command.command("show")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
def paper_show(doi: str, version: int | None) -> None:
    """Show details of a cached paper."""
    from astra.cli.text import console as _console

    console = _console()
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    paper = cache.get(doi, version)

    if not paper:
        console.print(f"[red]Error:[/red] Paper not found in cache: {doi}")
        if version:
            console.print(f"  (version {version})")
        console.print("\nUse [cyan]astra paper add[/cyan] to download the paper first.")
        raise SystemExit(1)

    meta = paper.metadata
    console.print(f"\n[bold]DOI:[/bold] {meta.doi}")
    if meta.version:
        console.print(f"[bold]Version:[/bold] {meta.version}")
    if meta.title:
        console.print(f"[bold]Title:[/bold] {meta.title}")
    if meta.authors:
        console.print(f"[bold]Authors:[/bold] {', '.join(meta.authors)}")
    console.print(f"[bold]SHA-256:[/bold] {meta.sha256}")
    console.print(f"[bold]Retrieved:[/bold] {meta.retrieved_at}")
    if meta.source_url:
        console.print(f"[bold]Source:[/bold] {meta.source_url}")
    console.print(f"[bold]Path:[/bold] {paper.pdf_path}")


@command.command("path")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
def paper_path(doi: str, version: int | None) -> None:
    """Print the path to a cached paper's PDF.

    Useful for piping to other tools or agents that need to read the PDF.
    """
    from astra.cli.text import console as _console

    console = _console()
    from astra.papers.cache import PaperCache

    cache = PaperCache()
    path = cache.get_path(doi, version)

    if not path:
        console.print(f"[red]Error:[/red] Paper not found: {doi}")
        raise SystemExit(1)

    # Print just the path (no formatting) for easy piping
    print(path)


@command.command("remove")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
def paper_remove(doi: str, version: int | None) -> None:
    """Remove a paper from the cache."""
    from astra.cli.text import console as _console

    console = _console()
    from astra.papers.cache import PaperCache

    cache = PaperCache()

    if not cache.has(doi, version):
        console.print(f"[red]Error:[/red] Paper not found: {doi}")
        raise SystemExit(1)

    cache.remove(doi, version)
    console.print("[green]✓[/green] Paper removed from cache")


@command.command("fetch-metadata")
@click.argument("doi", required=False)
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
@click.option("--all", "fetch_all", is_flag=True, help="Fetch metadata for all cached papers")
def paper_fetch_metadata(doi: str | None, version: int | None, fetch_all: bool) -> None:
    """Fetch metadata (title, authors) for cached papers.

    Uses DOI content negotiation to retrieve metadata from DOI.org.

    Examples:

        astra paper fetch-metadata 10.48550/arXiv.1706.03762

        astra paper fetch-metadata --all
    """
    from astra.cli.text import console as _console

    console = _console()
    from astra.papers.cache import PaperCache
    from astra.papers.download import fetch_doi_metadata

    cache = PaperCache()

    if fetch_all:
        papers = cache.list_papers()
        if not papers:
            console.print("[dim]No papers cached[/dim]")
            return

        updated = 0
        for paper in papers:
            meta = paper.metadata
            if meta.title and meta.authors:
                continue

            console.print(f"Fetching metadata for {meta.doi}...", end=" ")
            doi_meta = fetch_doi_metadata(meta.doi)

            if doi_meta.title or doi_meta.authors:
                cache.update_metadata(
                    meta.doi,
                    meta.version,
                    title=doi_meta.title,
                    authors=doi_meta.authors,
                )
                console.print(f"[green]✓[/green] {doi_meta.title or '(no title)'}")
                updated += 1
            else:
                console.print("[yellow]⚠[/yellow] No metadata found")

        console.print(f"\n[dim]Updated {updated} paper(s)[/dim]")
        return

    if not doi:
        console.print("[red]Error:[/red] Provide a DOI or use --all")
        raise SystemExit(1)

    if not cache.has(doi, version):
        console.print(f"[red]Error:[/red] Paper not found in cache: {doi}")
        raise SystemExit(1)

    console.print(f"Fetching metadata for {doi}...")
    doi_meta = fetch_doi_metadata(doi)

    if not doi_meta.title and not doi_meta.authors:
        console.print("[yellow]⚠[/yellow] No metadata found for this DOI")
        raise SystemExit(1)

    cache.update_metadata(doi, version, title=doi_meta.title, authors=doi_meta.authors)

    console.print("[green]✓[/green] Metadata updated:")
    if doi_meta.title:
        console.print(f"  Title: {doi_meta.title}")
    if doi_meta.authors:
        console.print(f"  Authors: {', '.join(doi_meta.authors)}")


@command.command("verify-quotes")
@click.argument("doi")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
def paper_verify_quotes(doi: str, version: int | None) -> None:
    """Verify multiple quotes from a cached paper in a single operation.

    Reads quote list from stdin as JSON. Extracts PDF text once and
    verifies all quotes against it.

    Input format (stdin):
        {"quotes": [{"text": "...", "page": N, "prefix": "...", "suffix": "..."}, ...]}

    Output format (stdout, JSON):
        {"doi": "...", "results": [...], "summary": {...}}

    Exit codes:
      0 - All quotes verified
      1 - Some quotes not found
      2 - Error (paper not cached, invalid input, etc.)
    """
    from astra.papers.cache import PaperCache
    from astra.verification.core import VerificationStatus, verify_quote_in_pdf
    from astra.verification.pdf import extract_text_from_pdf

    # Read JSON input from stdin
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            print(
                json.dumps(
                    {
                        "doi": doi,
                        "version": version,
                        "results": [],
                        "summary": {"total": 0, "verified": 0, "not_found": 0, "errors": 1},
                        "error": "No input provided on stdin",
                    }
                )
            )
            raise SystemExit(2)

        data = json.loads(input_data)
        quotes = data.get("quotes", [])
    except json.JSONDecodeError as e:
        print(
            json.dumps(
                {
                    "doi": doi,
                    "version": version,
                    "results": [],
                    "summary": {"total": 0, "verified": 0, "not_found": 0, "errors": 1},
                    "error": f"Invalid JSON input: {e}",
                }
            )
        )
        raise SystemExit(2)

    # Get paper from cache
    cache = PaperCache()
    cached_paper = cache.get(doi, version)

    if not cached_paper:
        print(
            json.dumps(
                {
                    "doi": doi,
                    "version": version,
                    "results": [],
                    "summary": {"total": len(quotes), "verified": 0, "not_found": 0, "errors": 1},
                    "error": f"Paper not in cache: {doi}",
                }
            )
        )
        raise SystemExit(2)

    # Extract text from PDF (ONCE)
    try:
        pdf = extract_text_from_pdf(cached_paper.pdf_path)
    except Exception as e:
        print(
            json.dumps(
                {
                    "doi": doi,
                    "version": version,
                    "results": [],
                    "summary": {"total": len(quotes), "verified": 0, "not_found": 0, "errors": 1},
                    "error": f"Failed to extract text from PDF: {e}",
                }
            )
        )
        raise SystemExit(2)

    # Verify each quote
    results = []
    verified_count = 0
    not_found_count = 0

    for idx, quote_data in enumerate(quotes):
        quote_text = quote_data.get("text", "")
        page_hint = quote_data.get("page")
        prefix = quote_data.get("prefix")
        suffix = quote_data.get("suffix")

        if not quote_text:
            results.append(
                {
                    "index": idx,
                    "text": "",
                    "status": "error",
                    "found_pages": [],
                    "message": "Empty quote text",
                }
            )
            continue

        status, found_pages, message = verify_quote_in_pdf(
            quote_text, pdf, page_hint, prefix, suffix
        )

        display_text = quote_text[:50] + "..." if len(quote_text) > 50 else quote_text

        results.append(
            {
                "index": idx,
                "text": display_text,
                "status": status.value,
                "found_pages": found_pages,
                "message": message,
            }
        )

        if status == VerificationStatus.VERIFIED:
            verified_count += 1
        else:
            not_found_count += 1

    # Output results
    output = {
        "doi": doi,
        "version": version,
        "results": results,
        "summary": {
            "total": len(quotes),
            "verified": verified_count,
            "not_found": not_found_count,
            "errors": 0,
        },
    }
    print(json.dumps(output))

    if not_found_count > 0:
        raise SystemExit(1)
    raise SystemExit(0)


@command.command("verify-quote")
@click.argument("doi")
@click.option("--quote", "-q", required=True, help="Exact quote text to verify")
@click.option("--version", "-v", type=int, help="Paper version (for arXiv papers)")
@click.option("--page", "-p", type=int, help="Expected page number (1-indexed)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def paper_verify_quote(
    doi: str, quote: str, version: int | None, page: int | None, output_json: bool
) -> None:
    """Verify a quote exists in a cached paper.

    Searches for the exact quote in the paper's text. Uses fuzzy matching
    to handle minor OCR/extraction differences.

    Exit codes:
      0 - Quote verified (found in paper)
      1 - Quote not found
      2 - Error (paper not cached, etc.)
    """
    from astra.cli.text import console as _console

    console = _console()
    from astra.papers.cache import PaperCache
    from astra.verification.core import VerificationStatus, verify_quote_in_pdf
    from astra.verification.pdf import extract_text_from_pdf

    cache = PaperCache()
    cached_paper = cache.get(doi, version)

    if not cached_paper:
        if output_json:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"Paper not in cache: {doi}",
                        "found_pages": [],
                        "expected_page": page,
                    }
                )
            )
        else:
            console.print(f"[red]Error:[/red] Paper not in cache: {doi}")
            console.print("Use [cyan]astra paper add[/cyan] first.")
        raise SystemExit(2)

    try:
        pdf = extract_text_from_pdf(cached_paper.pdf_path)
    except Exception as e:
        if output_json:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"Failed to extract text from PDF: {e}",
                        "found_pages": [],
                        "expected_page": page,
                    }
                )
            )
        else:
            console.print(f"[red]Error:[/red] Failed to extract text from PDF: {e}")
        raise SystemExit(2)

    status, found_pages, message = verify_quote_in_pdf(quote, pdf, page)

    if output_json:
        print(
            json.dumps(
                {
                    "status": status.value,
                    "found_pages": found_pages,
                    "expected_page": page,
                    "message": message,
                }
            )
        )
    else:
        if status == VerificationStatus.VERIFIED:
            console.print(f"[green]✓ Verified[/green] {message}")
        else:
            console.print(f"[red]✗ Not found[/red] {message}")

    raise SystemExit(0 if status == VerificationStatus.VERIFIED else 1)
