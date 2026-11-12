"""`astra paper add DOI [--version N] [--file PDF] [--email ADDRESS] | list [PATH] | verify
[PATH] | seek DOI QUOTE... [--version N] [--page N]`: the papers that the root's evidence cites
by DOI, kept in the cache, and the quotes it takes from them, or quotes given, with the extra
`[evidence]`. Text alone, as `info` is.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import click

from astra.cli import FAILED, environment, fail, write_report

if TYPE_CHECKING:
    from astra.evidence.quotes import Sought

EXTRA = ("pypdf", "rapidfuzz")
"""The packages of the extra `[evidence]`."""


@click.group("paper")
def command() -> None:
    """Keep the papers an analysis cites by DOI, and seek quotes in them.

    Papers are kept in the cache, by DOI and version. A quote is sought in its paper's text,
    within the page its location gives (`page=6`), or in the whole text. `verify` seeks the
    quotes an analysis's evidence takes, and one not found is a warning, never an error; `seek`
    seeks the quotes you give it, with no analysis. These commands need the extra [evidence]:
    pip install 'astra-tools[evidence]'.
    """
    # Text alone, with no --json.


@contextlib.contextmanager
def _evidence() -> Iterator[None]:
    """Stop with exit 2 where the extra isn't installed, a paper can't be got or read, or the
    analysis can't be read; and with exit 1 where it breaks a `MUST`."""
    from astra import api

    try:
        from astra.evidence import quotes  # noqa: F401  (imports the extra's two packages)
        from astra.evidence.papers import PaperError
    except ModuleNotFoundError as error:
        if error.name not in EXTRA:
            raise
        fail(
            f"`astra paper` needs the extra [evidence], whose {error.name} isn't installed: "
            "pip install 'astra-tools[evidence]'"
        )
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
@click.option(
    "--version",
    type=click.IntRange(min=1),
    metavar="N",
    help="The work's version, counted from 1, as the evidence gives it.",
)
@click.option(
    "--file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="PDF",
    help="Keep this PDF, instead of fetching the paper.",
)
@click.option(
    "--email",
    metavar="ADDRESS",
    help="Your email address, which Unpaywall asks for to find a paper that isn't arXiv's.",
)
def add(doi: str, version: int | None, file: Path | None, email: str | None) -> None:
    """Keep the paper of DOI in the cache.

    Without --file, an arXiv DOI (10.48550/arXiv.<id>) is fetched from arXiv, at --version
    where given, and any other from the open-access copy Unpaywall knows, which asks for
    --email. Exits 0 when the paper is kept, and 2 where it can't be got or isn't a PDF.
    """
    with _evidence():
        from astra.evidence import papers

        data = None if file is None else file.read_bytes()
        count = papers.add(doi, version, data=data, email=email)
    click.echo(f"Kept the paper of {papers.named(doi, version)} in the cache: {count} page(s).")


@command.command("list")
@click.argument("path", required=False, type=click.Path(file_okay=False, path_type=Path))
def list_(path: Path | None) -> None:
    """List each work the evidence of the analysis in PATH cites by DOI, and whether its paper
    is in the cache.

    PATH is the analysis's folder, the current one by default. Exits 0; 1 when the analysis
    breaks a MUST, which is shown as `astra validate` shows it; and 2 where it can't be read.
    """
    from astra import api

    with _evidence():
        from astra.evidence import papers

        cited = api.papers(path)
    for work in cited:
        named = work.doi + ("" if work.version is None else f" version {work.version}")
        if work.cached:
            click.echo(f"{named}: in the cache")
            continue
        click.echo(f"{named}: not in the cache: `{papers.command(work.doi, work.version)}`")
    if not cited:
        click.echo("The analysis's evidence cites no work by DOI.")


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
        warnings = api.quotes(path)
    from astra.cli.text.paper import show

    show(warnings)


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
