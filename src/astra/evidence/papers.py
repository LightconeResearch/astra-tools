"""The papers that evidence cites by `doi`, kept in the cache.

For a `doi`, the cited resource is the work's full text: here, its PDF. The cache keeps
one in its `papers` folder for each DOI and the `version` evidence gives, if any, as a `.pdf`
file, with a `.json` record of it beside (`Record`). `add` keeps one, from bytes the user has
or fetched through `urllib`: an arXiv DOI's from arXiv, at its version, and any other's from
the open-access PDF Unpaywall names as its best; for one fetched, the work's title and authors
come from doi.org. `pages` gives a PDF's text, page by page, through pypdf.
"""

from __future__ import annotations

import hashlib
import io
import json
import shlex
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from astra import cache, model

if TYPE_CHECKING:
    from astra.stack import Pointer, Stack

NAMESPACE = "papers"

PDF_SUFFIX = ".pdf"
RECORD_SUFFIX = ".json"

ARXIV = "10.48550/arxiv."
"""How the DOIs arXiv gives its papers begin, lowercased: `10.48550/arXiv.<id>`."""

AGENT = "astra-tools (https://github.com/astra-project/astra-tools)"
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


@dataclass(frozen=True)
class Record:
    """What the cache knows of a paper it keeps, beside its PDF."""

    doi: str
    version: int | None
    sha256: str  # the PDF's
    retrieved_at: str  # when it was kept, in UTC, as ISO 8601
    title: str | None = None
    authors: tuple[str, ...] = ()
    source_url: str | None = None  # where it was fetched from; None for a PDF given

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Record:
        return cls(
            data["doi"],
            data.get("version"),
            data["sha256"],
            data["retrieved_at"],
            data.get("title"),
            tuple(data.get("authors") or ()),
            data.get("source_url"),
        )


def evidence(stack: Stack) -> Iterator[tuple[Pointer, str, model.Evidence]]:
    """Each item of the root's evidence that cites a `doi`, with its pointer in the root's file
    and its DOI."""
    # The root's evidence, as a check covers the evidence of the analysis it is run on.
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
            found[key] = Cited(doi, item.version, get(doi, item.version) is not None)
    return tuple(found.values())


def get(doi: str, version: int | None) -> bytes | None:
    """The PDF the cache holds for `doi` at `version` (None for no version), or None."""
    return cache.get(NAMESPACE, _key(doi, version), PDF_SUFFIX)


def path(doi: str, version: int | None) -> Path | None:
    """The file of the PDF the cache holds for `doi` at `version`, or None."""
    return cache.path(NAMESPACE, _key(doi, version), PDF_SUFFIX)


def record(doi: str, version: int | None) -> Record | None:
    """The record of the paper the cache holds for `doi` at `version`, or None where it holds
    none, or a PDF kept without one."""
    if get(doi, version) is None:
        return None
    data = cache.get(NAMESPACE, _key(doi, version), RECORD_SUFFIX)
    return None if data is None else Record.from_json(json.loads(data))


def records() -> tuple[Record, ...]:
    """The record of every paper the cache holds, by DOI, then version."""
    found = [Record.from_json(json.loads(data)) for data in cache.values(NAMESPACE, RECORD_SUFFIX)]
    kept = [found_ for found_ in found if get(found_.doi, found_.version) is not None]
    return tuple(sorted(kept, key=lambda r: (r.doi.lower(), r.version or 0)))


def add(
    doi: str, version: int | None, *, data: bytes | None = None, email: str | None = None
) -> int:
    """Keep the PDF of `doi` at `version` in the cache, in place of any kept before, with its
    record: `data`, or where it is None, what is fetched with `email`, whose title and authors
    doi.org gives, where it can. Gives its number of pages. Raises PaperError where it can't be
    got, or isn't a PDF that pypdf reads, and CacheError where the cache can't be written."""
    source: str | None = None
    if data is None:
        data, source = _fetch(doi, version, email)
    count = len(_read(data).pages)
    title, authors = (None, ()) if source is None else _metadata(doi)
    kept = Record(
        doi,
        version,
        hashlib.sha256(data).hexdigest(),
        datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        title,
        authors,
        source,
    )
    key = _key(doi, version)
    cache.put(NAMESPACE, key, data, PDF_SUFFIX)
    cache.put(NAMESPACE, key, json.dumps(asdict(kept), indent=2).encode("utf-8"), RECORD_SUFFIX)
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


def _fetch(doi: str, version: int | None, email: str | None) -> tuple[bytes, str]:
    """What is got for `doi` at `version`, and from where: arXiv's PDF of an arXiv DOI,
    `10.48550/arXiv.<id>`, at `version` as `<id>v<version>`, or the latest; for any other, and
    only with no version, the open-access PDF Unpaywall, asked with `email`, names as its best.
    Raises PaperError where it can't be got."""
    if doi.lower().startswith(ARXIV):
        paper = urllib.parse.quote(doi[len(ARXIV) :], safe="/")
        at = "" if version is None else f"v{version}"
        url = f"https://arxiv.org/pdf/{paper}{at}"
        return _download(url), url
    # Unpaywall's email is the user's to give: only arXiv's versions.
    if version is not None:
        raise PaperError(
            f"only arXiv's papers can be fetched at a version: get version {version} of `{doi}` "
            "yourself and give it with --pdf"
        )
    if email is None:
        raise PaperError(
            f"`{doi}` isn't arXiv's, and Unpaywall, which finds its open-access copy, asks for "
            "your email address: give it with --email, or give the PDF with --pdf"
        )
    query = urllib.parse.urlencode({"email": email})
    asked = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='/')}?{query}"
    best = (json.loads(_download(asked)).get("best_oa_location") or {}).get("url_for_pdf")
    if not isinstance(best, str) or not best:
        raise PaperError(
            f"Unpaywall knows no open-access PDF of `{doi}`: get it yourself and give it with --pdf"
        )
    return _download(best), best


def _metadata(doi: str) -> tuple[str | None, tuple[str, ...]]:
    """The title and authors doi.org gives for `doi`, through content negotiation (CSL JSON);
    none where it can't be asked or says nothing."""
    url = f"https://doi.org/{urllib.parse.quote(doi, safe='/')}"
    try:
        data = json.loads(_download(url, "application/vnd.citationstyles.csl+json"))
    except (PaperError, ValueError):
        return None, ()
    if not isinstance(data, dict):
        return None, ()
    title = data.get("title")
    if isinstance(title, list):
        title = title[0] if title else None
    authors = tuple(
        " ".join(part for part in (person.get("given"), person.get("family")) if part)
        or person.get("literal", "")
        for person in data.get("author") or ()
        if isinstance(person, dict)
    )
    return (title if isinstance(title, str) else None), tuple(a for a in authors if a)


def _download(url: str, accept: str | None = None) -> bytes:
    headers = {"User-Agent": AGENT} if accept is None else {"User-Agent": AGENT, "Accept": accept}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data: bytes = response.read()
            return data
    except urllib.error.HTTPError as error:
        raise PaperError(
            f"{url} answered {error.code} {error.reason}: give the PDF with --pdf"
        ) from error
    except OSError as error:  # urllib's URLError, and a timeout, are OSErrors
        reason = getattr(error, "reason", error)
        raise PaperError(
            f"can't reach {url}: {reason}; check the network, or give the PDF with --pdf"
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
                f"the paper's PDF can't be read ({error}): give a whole one with --pdf"
            ) from error
    raise PaperError("the paper isn't a PDF, which begins `%PDF-`: give its PDF with --pdf")


def _key(doi: str, version: int | None) -> str:
    """The cache's key for `doi` at `version`: DOI names are case-insensitive."""
    return json.dumps([doi.lower(), version])
