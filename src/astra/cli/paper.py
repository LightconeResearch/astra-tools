"""`astra paper add DOI [-v N] [--pdf PDF] [--email ADDRESS] | list | show DOI [-v N] | path
DOI [-v N] | verify-quotes DOI [-v N] | verify [PATH] | seek DOI QUOTE... [--version N] [--page
N]`: the papers kept in the cache, by DOI, and the quotes sought in them: those an analysis's
evidence takes, or those given.
"""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import click

from astra.cli import FAILED, USAGE, environment, fail, write_report

if TYPE_CHECKING:
    from astra.evidence.quotes import Sought

VERSION = click.option(
    "-v",
    "--version",
    type=click.IntRange(min=1),
    metavar="N",
    help="The work's version, counted from 1, as the evidence gives it (an arXiv paper's).",
)


@click.group("paper")
def command() -> None:
    """Keep papers by DOI in the cache, and seek quotes in them.

    Papers are kept in the cache, by DOI and version. A quote is sought in its paper's text.
    `verify` seeks the quotes an analysis's evidence takes; `verify-quotes` and `seek` seek
    the quotes you give.
    """


@contextlib.contextmanager
def _evidence() -> Iterator[None]:
    """Stop with exit 2 where a paper can't be got or read, or the analysis can't be read; and
    with exit 1 where it breaks a `MUST`."""
    from astra import api
    from astra.evidence.papers import PaperError

    with environment():
        try:
            yield
        except api.InvalidAnalysisError as error:
            write_report(error.report, False)
            raise click.exceptions.Exit(FAILED) from None
        except PaperError as error:
            fail(str(error))


@command.command("add")
@click.argument("doi")
@VERSION
@click.option(
    "--pdf",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="PATH",
    help="Use this local PDF instead of downloading the paper.",
)
@click.option(
    "--email",
    metavar="ADDRESS",
    help="Your email address, which Unpaywall asks for to find a paper that isn't arXiv's.",
)
def add(doi: str, version: int | None, pdf: Path | None, email: str | None) -> None:
    """Add a paper to the cache by DOI.

    An arXiv DOI (10.48550/arXiv.<id>) is downloaded from arXiv, at --version where given, and
    any other from the open-access copy Unpaywall knows, which asks for --email; --pdf keeps a
    PDF you have instead. A paper already in the cache is left as it is. Exits 0 when the
    paper is in the cache, and 2 where it can't be got or isn't a PDF.

    Examples:

        astra paper add 10.48550/arXiv.1706.03762 --version 7

        astra paper add 10.1038/s41586-023-06221-2 --email you@example.org

        astra paper add 10.1234/example --pdf ./local_paper.pdf
    """
    with _evidence():
        from astra.evidence import papers

        if papers.get(doi, version) is not None:
            click.echo(f"Paper already cached: {doi}")
            click.echo(f"  Path: {papers.path(doi, version)}")
            kept = papers.record(doi, version)
            if kept is not None and kept.title:
                click.echo(f"  Title: {kept.title}")
            return
        if pdf is not None:
            click.echo(f"Adding paper from local file: {pdf}")
            papers.add(doi, version, data=pdf.read_bytes())
            click.echo("✓ Paper added to cache")
        else:
            click.echo(f"Downloading paper: {doi}")
            if version is not None:
                click.echo(f"  Version: {version}")
            papers.add(doi, version, email=email)
            click.echo("✓ Paper downloaded and cached")
        kept = papers.record(doi, version)
    click.echo(f"  DOI: {doi}")
    if version is not None:
        click.echo(f"  Version: {version}")
    if kept is not None and kept.title:
        click.echo(f"  Title: {kept.title}")
    click.echo(f"  Path: {papers.path(doi, version)}")
    if kept is not None:
        click.echo(f"  SHA-256: {kept.sha256[:16]}...")


@command.command("list")
def list_() -> None:
    """List all cached papers."""
    with _evidence():
        from astra.evidence import papers

        kept = papers.records()
    from astra.cli.text.paper import show_papers

    show_papers(kept)


@command.command("show")
@click.argument("doi")
@VERSION
def show(doi: str, version: int | None) -> None:
    """Show details of a cached paper. Exits 1 where it isn't in the cache."""
    with _evidence():
        from astra.evidence import papers

        kept = papers.record(doi, version)
        where = papers.path(doi, version)
    if where is None:
        click.echo(f"Error: Paper not found in cache: {doi}" + _version(version))
        click.echo(f"Use `{papers.command(doi, version)}` to download the paper first.")
        raise click.exceptions.Exit(FAILED)
    click.echo(f"DOI: {doi}")
    if version is not None:
        click.echo(f"Version: {version}")
    if kept is not None:
        if kept.title:
            click.echo(f"Title: {kept.title}")
        if kept.authors:
            click.echo(f"Authors: {', '.join(kept.authors)}")
        click.echo(f"SHA-256: {kept.sha256}")
        click.echo(f"Retrieved: {kept.retrieved_at}")
        if kept.source_url:
            click.echo(f"Source: {kept.source_url}")
    click.echo(f"Path: {where}")


@command.command("path")
@click.argument("doi")
@VERSION
def path_(doi: str, version: int | None) -> None:
    """Print the path to a cached paper's PDF.

    Useful for piping to other tools or agents that need to read the PDF. Exits 1 where it
    isn't in the cache.
    """
    with _evidence():
        from astra.evidence import papers

        where = papers.path(doi, version)
    if where is None:
        click.echo(f"Error: Paper not found: {doi}" + _version(version), err=True)
        raise click.exceptions.Exit(FAILED)
    click.echo(str(where))


@command.command("verify-quotes")
@click.argument("doi")
@VERSION
def verify_quotes(doi: str, version: int | None) -> None:
    """Verify multiple quotes from a cached paper in a single operation.

    Reads the quotes from stdin as JSON, extracts the PDF's text once, and seeks each quote
    in the whole text, as `astra paper verify` does; a quote's page only orders its pages
    found, and its prefix and suffix are read but not sought.

    \b
    Input format (stdin):
        {"quotes": [{"text": "...", "page": N, "prefix": "...", "suffix": "..."}, ...]}
    Output format (stdout, JSON):
        {"doi": "...", "version": N, "results": [...], "summary": {...}}
    Exit codes:
      0 - All quotes verified
      1 - Some quotes not found
      2 - Error (paper not cached, invalid input, etc.)
    """
    from astra.evidence import papers
    from astra.evidence.quotes import seek

    def stop(error: str, total: int = 0) -> NoReturn:
        summary = {"total": total, "verified": 0, "not_found": 0, "errors": 1}
        out: dict[str, Any] = {"doi": doi, "version": version, "results": [], "summary": summary}
        out["error"] = error
        click.echo(json.dumps(out))
        raise click.exceptions.Exit(USAGE)

    text = sys.stdin.read()
    if not text.strip():
        stop("No input provided on stdin")
    try:
        quotes = json.loads(text).get("quotes", [])
    except (ValueError, AttributeError) as error:
        stop(f"Invalid JSON input: {error}")
    if not isinstance(quotes, list):
        stop("Invalid JSON input: `quotes` isn't a list")
    with environment():
        data = papers.get(doi, version)
    if data is None:
        stop(f"Paper not in cache: {doi}", len(quotes))
    try:
        pages = papers.pages(data)
    except papers.PaperError as error:
        stop(f"Failed to extract text from PDF: {error}", len(quotes))
    results: list[dict[str, Any]] = []
    verified = not_found = errors = 0
    for index, quote in enumerate(quotes):
        exact = quote.get("text", "") if isinstance(quote, dict) else ""
        if not isinstance(exact, str) or not exact.split():
            message = "Empty quote text"
            results.append(_result(index, "", "error", [], message))
            errors += 1
            continue
        found = _pages(seek(exact, pages), quote.get("page"))
        shown = exact[:50] + "..." if len(exact) > 50 else exact
        if found:
            verified += 1
            message = f"Quote verified on page(s) {found}"
            results.append(_result(index, shown, "verified", found, message))
        else:
            not_found += 1
            message = f"Quote not found in PDF: '{exact[:50]}...'"
            results.append(_result(index, shown, "not_found", [], message))
    summary = {
        "total": len(quotes),
        "verified": verified,
        "not_found": not_found,
        "errors": errors,
    }
    click.echo(json.dumps({"doi": doi, "version": version, "results": results, "summary": summary}))
    if not_found or errors:
        raise click.exceptions.Exit(FAILED)


def _pages(sought: Sought, hint: object) -> list[int]:
    """The pages a quote is found on, the page hinted first where it is one of them."""
    found = sorted({page for first, last in sought.pages for page in range(first, last + 1)})
    if sought.found and not found:  # across more than two pages
        found = []
    if isinstance(hint, int) and hint in found:
        found.remove(hint)
        found.insert(0, hint)
    return found if sought.found else []


def _result(index: int, text: str, status: str, pages: list[int], message: str) -> dict[str, Any]:
    return {
        "index": index,
        "text": text,
        "status": status,
        "found_pages": pages,
        "message": message,
    }


def _version(version: int | None) -> str:
    return "" if version is None else f" (version {version})"


def show_quotes(folder: Path) -> bool:
    """Seek each quote the evidence of the analysis in `folder` takes from a paper, and print
    what `astra paper verify` prints; whether none is an error (`validate --verify-evidence`)."""
    from astra import api

    with _evidence():
        diagnostics = api.quotes(folder)
    from astra.cli.text.paper import show as show_diagnostics

    show_diagnostics(diagnostics)
    return not any(diagnostic.level == "error" for diagnostic in diagnostics)


@command.command("verify")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
def verify(path: Path | None) -> None:
    """Seek each quote that the evidence of the analysis in PATH takes from a work it cites by
    DOI, in its paper in the cache.

    PATH is the analysis's folder, the current one by default. A paper not in the cache, and a
    quote not found in its paper, are warnings, shown as `astra validate` shows them. Exits 0
    whatever it finds; 1 when the analysis breaks a MUST, which is shown as `astra validate`
    shows it; and 2 where it can't be read.
    """
    from astra import api

    with _evidence():
        diagnostics = api.quotes(path)
    from astra.cli.text.paper import show as show_diagnostics

    show_diagnostics(diagnostics)


@command.command("seek")
@click.argument("doi")
@click.argument("quote", nargs=-1, required=True)
@click.option(
    "--version",
    type=click.IntRange(min=1),
    metavar="N",
    help="The work's version, counted from 1, as the evidence gives it.",
)
@click.option(
    "--page",
    type=click.IntRange(min=1),
    metavar="N",
    help="Seek each quote within this page, counted from 1, not in the whole text.",
)
def seek(doi: str, quote: tuple[str, ...], version: int | None, page: int | None) -> None:
    """Seek each QUOTE in the paper of DOI in the cache, as `astra paper verify` seeks a quote
    that evidence takes from it, with no analysis.

    Each quote is sought within --page where given, or in the whole text, and shown with the
    pages it is found on: the page that a location such as `page=6` gives. Exits 0 when each
    quote is found; 1 when one isn't; and 2 where the paper isn't in the cache, can't be read,
    or has no page --page.
    """
    from astra import api

    if any(not text.split() for text in quote):
        raise click.BadParameter("a quote can't be blank", param_hint="QUOTE")
    with _evidence():
        try:
            found = api.seek(doi, *quote, version=version, page=page)
        except api.RequestError as error:
            raise click.BadParameter(str(error), param_hint="'--page'") from None
    for sought in found:
        click.echo(f"{_where(sought)}: {' '.join(sought.exact.split())}")
    if not all(sought.found for sought in found):
        raise click.exceptions.Exit(FAILED)


def _where(sought: Sought) -> str:
    """Where a quote is found, or where it was sought and not found."""
    if not sought.found:
        where = "in the whole text" if sought.page is None else f"on page {sought.page}"
        return f"not found {where}"
    if not sought.pages:
        return "found in the whole text, across more than two pages"
    named = [str(first) if first == last else f"{first}-{last}" for first, last in sought.pages]
    listed = named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"
    if sought.pages[0][0] != sought.pages[0][1]:
        return f"found across pages {listed}"
    return f"found on page{'s' if len(named) > 1 else ''} {listed}"
