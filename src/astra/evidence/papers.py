"""The papers that evidence cites by `doi` (§14), kept in the cache (design §4.9).

For a `doi`, the cited resource is the work's full text (§14): here, its PDF. The cache keeps
one in its `papers` folder for each DOI and the `version` evidence gives, if any. `add` keeps
one, from bytes the user has or fetched through `urllib`: an arXiv DOI's from arXiv, at its
version, and any other's from the open-access PDF Unpaywall names as its best. `pages` gives a
PDF's text, page by page, through pypdf.
"""

from __future__ import annotations

import io
import json
import shlex
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from astra import cache, model

if TYPE_CHECKING:
    from astra.stack import Pointer, Stack

NAMESPACE = "papers"

ARXIV = "10.48550/arxiv."
"""How the DOIs arXiv gives its papers begin, lowercased: `10.48550/arXiv.<id>`."""

AGENT = "astra-tools (https://github.com/LightconeResearch/astra-tools)"
"""The User-Agent of each request: some servers refuse Python's own."""

TIMEOUT = 60
"""How long a request may wait for an answer, in seconds."""


class PaperError(Exception):
    """A paper that can't be got, or bytes that aren't a PDF; the message says what to do."""


@dataclass(frozen=True)
class Cited:
    """A work the root's evidence cites by DOI, at a version or none, and whether the cache
    holds its paper."""

    doi: str
    version: int | None
    cached: bool


def evidence(stack: Stack) -> Iterator[tuple[Pointer, str, model.Evidence]]:
    """Each item of the root's evidence that cites a `doi`, with its pointer in the root's file
    and its DOI."""
    # The root's evidence, as a check covers "the evidence of the analysis it is run
    # on" (§20 *Evidence*).
    analysis = stack.analysis(stack.root)
    for field, insights in (
        ("prior_insights", analysis.prior_insights),
        ("findings", analysis.findings),
    ):
        for id_, insight in insights.items():
            for index, item in enumerate(insight.evidence):
                if item.doi is not None:
                    yield (field, id_, "evidence", index), item.doi, item


def cited(stack: Stack) -> tuple[Cited, ...]:
    """Each work the root's evidence cites by DOI, at each version it cites, once, in the order
    the file first cites it, and whether the cache holds its paper."""
    found: dict[str, Cited] = {}
    for _, doi, item in evidence(stack):
        key = _key(doi, item.version)
        if key not in found:
            found[key] = Cited(doi, item.version, cache.get(NAMESPACE, key) is not None)
    return tuple(found.values())


def get(doi: str, version: int | None) -> bytes | None:
    """The PDF the cache holds for `doi` at `version` (None for no version), or None."""
    return cache.get(NAMESPACE, _key(doi, version))


def add(
    doi: str, version: int | None, *, data: bytes | None = None, email: str | None = None
) -> int:
    """Keep the PDF of `doi` at `version` in the cache, in place of any kept before: `data`, or
    where it is None, what is fetched with `email`. Gives its number of pages. Raises
    PaperError where it can't be got, or isn't a PDF that pypdf reads, and CacheError where the
    cache can't be written."""
    if data is None:
        data = _fetch(doi, version, email)
    count = len(_read(data).pages)
    cache.put(NAMESPACE, _key(doi, version), data)
    return count


def pages(data: bytes) -> tuple[str, ...]:
    """The text of each page of the PDF `data`, in order, as pypdf extracts it."""
    return tuple(page.extract_text() for page in _read(data).pages)


def named(doi: str, version: int | None) -> str:
    """`doi` at `version`, as messages name it: in backticks, with its version, if any."""
    return f"`{doi}`" + ("" if version is None else f" version {version}")


def command(doi: str, version: int | None) -> str:
    """The command that keeps the paper of `doi` at `version`: `EVIDENCE_PAPER_MISSING`'s
    message and `astra paper list` both give it."""
    option = "" if version is None else f" --version {version}"
    return f"astra paper add {shlex.quote(doi)}{option}"


def _fetch(doi: str, version: int | None, email: str | None) -> bytes:
    """What is got for `doi` at `version`: arXiv's PDF of an arXiv DOI, `10.48550/arXiv.<id>`,
    at `version` as `<id>v<version>`, or the latest; for any other, and only with no version,
    the open-access PDF Unpaywall, asked with `email`, names as its best. Raises PaperError
    where it can't be got."""
    if doi.lower().startswith(ARXIV):
        paper = urllib.parse.quote(doi[len(ARXIV) :], safe="/")
        at = "" if version is None else f"v{version}"
        return _download(f"https://arxiv.org/pdf/{paper}{at}")
    # Unpaywall's email is the user's to give: only arXiv's versions.
    if version is not None:
        raise PaperError(
            f"only arXiv's papers can be fetched at a version: get version {version} of `{doi}` "
            "yourself and give it with --file"
        )
    if email is None:
        raise PaperError(
            f"`{doi}` isn't arXiv's, and Unpaywall, which finds its open-access copy, asks for "
            "your email address: give it with --email, or give the PDF with --file"
        )
    query = urllib.parse.urlencode({"email": email})
    record = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='/')}?{query}"
    url = (json.loads(_download(record)).get("best_oa_location") or {}).get("url_for_pdf")
    if not url:
        raise PaperError(
            f"Unpaywall knows no open-access PDF of `{doi}`: get it yourself and give it with "
            "--file"
        )
    return _download(url)


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data: bytes = response.read()
            return data
    except urllib.error.HTTPError as error:
        raise PaperError(
            f"{url} answered {error.code} {error.reason}: give the PDF with --file"
        ) from error
    except OSError as error:  # urllib's URLError, and a timeout, are OSErrors
        reason = getattr(error, "reason", error)
        raise PaperError(
            f"can't reach {url}: {reason}; check the network, or give the PDF with --file"
        ) from error


def _read(data: bytes) -> PdfReader:
    """The PDF `data`, as pypdf reads it; PaperError where it isn't one."""
    # A PDF is bytes that begin `%PDF-` and whose pages pypdf reads.
    if data.startswith(b"%PDF-"):
        try:
            reader = PdfReader(io.BytesIO(data))
            len(reader.pages)  # reads the page tree
            return reader
        except PyPdfError as error:
            raise PaperError(
                f"the paper's PDF can't be read ({error}): give a whole one with --file"
            ) from error
    raise PaperError("the paper isn't a PDF, which begins `%PDF-`: give its PDF with --file")


def _key(doi: str, version: int | None) -> str:
    """The cache's key for `doi` at `version`: DOI names are case-insensitive."""
    return json.dumps([doi.lower(), version])
