"""Quotes sought in the papers they are taken from, advisory only.

For a `doi`, the cited resource is the work's full text, and with both a `quote` and a
`location`, the quote is sought within the location. `verify` seeks each quote's `exact`
in the text of the work's PDF, kept in the cache by `astra paper add` (`papers`): within the
page that a PDF fragment identifier's `page=` gives (RFC 8118), or
in the whole text. Its warnings are codes of astra-tools' own, outside `rules.json`: always
warnings, which never change a verdict, a status or an exit code. `seek` seeks a quote given,
with no analysis, as `verify` seeks one, and says on which pages it is found (`Sought`).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rapidfuzz import fuzz

from astra import model
from astra.diagnostics import Diagnostic
from astra.evidence import papers

if TYPE_CHECKING:
    from astra.stack import Pointer, Stack

PAPER_MISSING = "EVIDENCE_PAPER_MISSING"
"""A quote's paper isn't in the cache, so the quote can't be sought."""

QUOTE_NOT_FOUND = "EVIDENCE_QUOTE_NOT_FOUND"
"""A quote isn't in its paper's text, where it was sought."""

THRESHOLD = 90
"""How well, out of 100, the text sought must match a quote for it to be found: rapidfuzz's
score of the best match of the quote in that text."""

PDF = (None, "http://tools.ietf.org/rfc/rfc3778")
"""The `conforms_to` of a PDF fragment identifier: none, or the IRI Web Annotation gives it."""


@dataclass(frozen=True)
class Sought:
    """A quote, its `exact`, sought in a paper within `page`, counted from 1, or in its whole
    text where `page` is None (`seek`): whether it is `found` there, and each run of `pages` it
    is on, as its first and last. Those are `page` itself or, in the whole text, each page it is
    on alone; on none alone, each two pages it runs across; and none where it isn't found, or
    runs across more than two."""

    exact: str
    page: int | None
    found: bool
    pages: tuple[tuple[int, int], ...]


def verify(stack: Stack) -> tuple[Diagnostic, ...]:
    """A warning for each item of the root's evidence citing a `doi` with a `quote` whose paper
    isn't in the cache (`EVIDENCE_PAPER_MISSING`, at its `doi`), or whose `exact` isn't found
    where it is sought (`EVIDENCE_QUOTE_NOT_FOUND`, at its `quote`); nothing for one found.
    Reads only the cache: `papers.add` keeps a paper."""
    # Only the cache is read.
    found: list[Diagnostic] = []
    texts: dict[tuple[str, int | None], tuple[str, ...] | None] = {}
    for pointer, doi, item in papers.evidence(stack):
        if item.quote is None:
            continue
        if (doi, item.version) not in texts:
            data = papers.get(doi, item.version)
            texts[doi, item.version] = None if data is None else papers.pages(data)
        pages = texts[doi, item.version]
        named = papers.named(doi, item.version)
        if pages is None:
            message = f"the paper of {named} isn't in the cache, so its quote isn't sought"
            message += f": run `{papers.command(doi, item.version)}`"
            found.append(_warning(PAPER_MISSING, message, stack, (*pointer, "doi")))
            continue
        page = _page(item.location)
        sought = _within(pages, page)
        if _found(item.quote.exact, " ".join(sought)):
            continue
        where = "in its whole text" if page is None else f"on page {page}, as its location says"
        if not sought:
            where += f", but the PDF has {len(pages)} page(s)"
        message = f"the quote isn't found in the paper of {named}, sought {where}"
        found.append(_warning(QUOTE_NOT_FOUND, message, stack, (*pointer, "quote")))
    return tuple(sorted(found, key=lambda d: (d.location.line or 0, d.location.column or 0)))


def seek(exact: str, pages: tuple[str, ...], page: int | None = None) -> Sought:
    """The quote `exact` sought in the paper whose pages' text is `pages`, as `verify` seeks a
    quote: within `page`, counted from 1, or in the whole text where it is None."""
    if not _found(exact, " ".join(_within(pages, page))):
        return Sought(exact, page, False, ())
    if page is not None:
        return Sought(exact, page, True, ((page, page),))
    found = tuple((n, n) for n, text in enumerate(pages, 1) if _found(exact, text))
    if not found:  # on no page alone
        pairs = range(1, len(pages))
        found = tuple((n, n + 1) for n in pairs if _found(exact, " ".join(pages[n - 1 : n + 1])))
    return Sought(exact, page, True, found)


def _within(pages: tuple[str, ...], page: int | None) -> tuple[str, ...]:
    """The pages a quote is sought within: `page`, counted from 1, or all of them where it is
    None; none where the paper hasn't that page."""
    return pages if page is None else pages[page - 1 : page]


def _page(location: model.FragmentSelector | None) -> int | None:
    """The page, counted from 1, that the first `page=` of a PDF fragment identifier gives, its
    parameters joined with `&`; None where the location gives none or follows another
    syntax."""
    # Any other location is sought in the whole text.
    if location is None or location.conforms_to not in PDF:
        return None
    for parameter in location.value.split("&"):
        name, _, value = parameter.partition("=")
        if name == "page" and value.isascii() and value.isdigit():
            return int(value)
    return None


def _found(exact: str, text: str) -> bool:
    """Whether `exact` is in `text` to within THRESHOLD, both read alike: every run of
    whitespace, line breaks included, made one space, and a ligature such as `ﬁ`, which a PDF's
    text often holds, its letters (NFKC)."""
    # How a quote counts as found.
    exact, text = (" ".join(unicodedata.normalize("NFKC", s).split()) for s in (exact, text))
    # partial_ratio matches the shorter of the two inside the longer: a text shorter than the
    # quote is compared whole.
    score = fuzz.partial_ratio(exact, text) if len(text) >= len(exact) else fuzz.ratio(exact, text)
    return score >= THRESHOLD


def _warning(code: str, message: str, stack: Stack, pointer: Pointer) -> Diagnostic:
    """`code`'s warning at `pointer` in the root's file: a code of astra-tools' own, always a
    warning."""
    return Diagnostic(code, "warning", message, stack.location(stack.root, pointer))
