"""Quotes against papers: papers kept in the cache by DOI and
version, and each quote sought in its paper's text, within the page a PDF fragment identifier
gives, on what `astra.evidence`, `api.papers`, `api.quotes`, `api.seek` and `astra paper`
promise. No test
reaches the network: a paper is given as a file, or `urllib` is answered from the test's own
bytes.
"""

from __future__ import annotations

import io
import json
import urllib.request
from collections.abc import Mapping
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.cli import main
from astra.diagnostics import Catalogue, Diagnostic, json_pointer
from astra.evidence import papers, quotes
from tests.conftest import MINIMAL, repository
from tests.spec import DOCUMENTS


def pdf(*pages: tuple[str, ...]) -> bytes:
    """A PDF whose pages each show their lines, in Helvetica: a catalogue, a page tree, each
    page with its text stream, a font, and the cross-reference table that finds them."""
    font = 3 + 2 * len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for i, lines in enumerate(pages):
        resources = f"<< /Font << /F1 {font} 0 R >> >>"
        page = f"/Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R"
        objects.append(f"<< /Type /Page {page} /Resources {resources} >>".encode())
        text = "BT /F1 12 Tf 14 TL 72 720 Td " + " ".join(f"({line}) Tj T*" for line in lines)
        stream = f"{text} ET".encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    table = b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    size, start = len(objects) + 1, len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n%s" % (size, table)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, start)
    return bytes(out)


DOI = "10.5555/12345678"
"""The specification's example of a DOI."""

PAGE_1 = ("Random forests stay accurate as label noise grows.", "We measured it on held-out data.")
PAGE_2 = ("In every experiment, the forest lost less", "than one point of accuracy at 20% noise.")
PAPER = pdf(PAGE_1, PAGE_2)
"""A two-page paper: the quote `ACROSS` is on page 2, across a line break."""

ACROSS = "the forest lost less than one point of accuracy"


def evidence(*items: str) -> str:
    """Evidence items, each a flow map, as an insight's list."""
    return "".join(f"      - {item}\n" for item in items)


def cites(exact: str, location: str = "", doi: str = DOI) -> str:
    """An item citing `doi` with the quote `exact`, and `location` as a flow map, if any."""
    found = f", location: {location}" if location else ""
    return f'{{doi: "{doi}", quote: {{exact: "{exact}"}}{found}}}'


ANALYSIS = (
    MINIMAL
    + "prior_insights:\n  whole:\n    claim: The forest resists noise.\n    evidence:\n"
    + evidence(cites(PAGE_1[0]), cites(ACROSS), cites("the forest gained two points of accuracy"))
    + "  paged:\n    claim: The forest resists noise.\n    evidence:\n"
    + evidence(
        cites(ACROSS, "{value: page=2}"),
        cites(ACROSS, "{value: page=1}"),
        cites(ACROSS, '{value: "page=2&search=%22label%20noise%22"}'),
        cites(ACROSS, '{value: page=1, conforms_to: "http://tools.ietf.org/rfc/rfc3778"}'),
        cites(ACROSS, '{value: "char=0,10", conforms_to: "http://tools.ietf.org/rfc/rfc5147"}'),
        cites(ACROSS, "{value: nameddest=results}"),
        cites(ACROSS, "{value: page=3}"),
    )
    + "  uncached:\n    claim: The forest resists noise.\n    evidence:\n"
    + evidence(
        cites(ACROSS, doi="10.5555/87654321"),
        f'{{doi: "{DOI}", version: 2, quote: {{exact: "{ACROSS}"}}}}',
        "{doi: 10.5555/87654321}",
    )
    + "findings:\n  arxiv:\n    claim: The forest resists noise.\n    evidence:\n"
    + evidence(cites(ACROSS, doi="10.48550/arXiv.2101.00001"))
)
"""An analysis whose evidence takes quotes from `PAPER`, kept in the cache, and from works
whose papers aren't."""


@pytest.fixture(scope="module")
def verified(tmp_path_factory: pytest.TempPathFactory) -> Mapping[str, Diagnostic]:
    """`api.quotes` on `ANALYSIS`, with `PAPER` kept for `DOI` and, in another case, for the
    arXiv DOI the findings cite: each warning by its pointer."""
    top = repository(tmp_path_factory.mktemp("quotes"), {"astra.yaml": ANALYSIS})
    assert papers.add(DOI, None, data=PAPER) == 2
    papers.add("10.48550/arxiv.2101.00001", None, data=PAPER)
    assert api.validate(top).diagnostics == ()
    return {d.location.pointer: d for d in api.quotes(top)}


def at(insight: str, index: int, field: str) -> str:
    return json_pointer(("prior_insights", insight, "evidence", index, field))


def test_a_quote_in_its_paper_gives_nothing(verified: Mapping[str, Diagnostic]) -> None:
    """The quote is sought in the work's full text, its line breaks evened out."""
    assert at("whole", 0, "quote") not in verified
    assert at("whole", 1, "quote") not in verified  # across a line break


def test_a_quote_not_in_its_paper_is_a_warning(verified: Mapping[str, Diagnostic]) -> None:
    """A quote not found is an `EVIDENCE_` warning, at the evidence's `quote`."""
    found = verified[at("whole", 2, "quote")]
    assert (found.code, found.level) == ("EVIDENCE_QUOTE_NOT_FOUND", "warning")
    assert "sought in its whole text" in found.message
    assert (found.location.file, found.location.line) == ("astra.yaml", 14)


def test_a_quote_is_sought_within_its_page(verified: Mapping[str, Diagnostic]) -> None:
    """With both a quote and a location, the quote is sought within the location; a PDF
    fragment identifier's `page=6` counts pages from 1."""
    assert at("paged", 0, "quote") not in verified
    assert "sought on page 1" in verified[at("paged", 1, "quote")].message


def test_a_pdf_fragment_identifiers_parameters(verified: Mapping[str, Diagnostic]) -> None:
    """PDF parameters are joined with `&`, and RFC 3778's IRI means the same as no `conforms_to`."""
    assert at("paged", 2, "quote") not in verified
    assert "sought on page 1" in verified[at("paged", 3, "quote")].message


def test_a_location_that_gives_no_page_is_the_whole_text(
    verified: Mapping[str, Diagnostic],
) -> None:
    """Another syntax's fragment, and a PDF fragment without `page=`, give no page: the
    cited resource is the work's full text."""
    assert at("paged", 4, "quote") not in verified
    assert at("paged", 5, "quote") not in verified


def test_a_page_the_paper_hasnt_holds_no_quote(verified: Mapping[str, Diagnostic]) -> None:
    found = verified[at("paged", 6, "quote")]
    assert found.code == "EVIDENCE_QUOTE_NOT_FOUND"
    assert "sought on page 3" in found.message and "has 2 page(s)" in found.message


def test_a_paper_not_in_the_cache_is_a_warning(verified: Mapping[str, Diagnostic]) -> None:
    """At the evidence's `doi`, saying how to add the paper at the version cited; evidence
    without a quote seeks nothing."""
    missing = verified[at("uncached", 0, "doi")]
    assert (missing.code, missing.level) == ("EVIDENCE_PAPER_MISSING", "warning")
    assert "`astra paper add 10.5555/87654321`" in missing.message
    version = verified[at("uncached", 1, "doi")]  # kept without a version, not as version 2
    assert "`astra paper add 10.5555/12345678 --version 2`" in version.message
    assert not any(pointer.startswith(at("uncached", 2, "")) for pointer in verified)


def test_a_doi_is_read_without_its_case(verified: Mapping[str, Diagnostic]) -> None:
    pointer = json_pointer(("findings", "arxiv", "evidence", 0, "quote"))
    assert not any(found.startswith(pointer) for found in verified)


def test_the_warnings_are_astra_tools_own(verified: Mapping[str, Diagnostic]) -> None:
    """`EVIDENCE_` warnings, outside `rules.json`, which leave the analysis valid."""
    assert set(verified) == {
        at("whole", 2, "quote"),
        at("paged", 1, "quote"),
        at("paged", 3, "quote"),
        at("paged", 6, "quote"),
        at("uncached", 0, "doi"),
        at("uncached", 1, "doi"),
    }
    codes = {found.code for found in verified.values()}
    assert codes == {quotes.PAPER_MISSING, quotes.QUOTE_NOT_FOUND}
    assert not codes & set(Catalogue.load().rules)


def test_astra_specs_insights_fixture(tmp_path: Path) -> None:
    """astra-spec's `Analysis-006-insights.yaml` cites three works by DOI, the first at version 2
    with a quote on page 6 (`page=6&search=…`)."""
    fixture = DOCUMENTS / "valid" / "Analysis-006-insights.yaml"
    top = repository(tmp_path, {"astra.yaml": fixture.read_bytes()})
    assert [(work.doi, work.version, work.cached) for work in api.papers(top)] == [
        (DOI, 2, False),
        ("10.978.8889637/173", None, False),
        ("10.3929/ethz-a- 007549606", None, False),
    ]
    pointer = "/prior_insights/forests_resist_noise/evidence/0/doi"
    assert [(d.code, d.location.pointer) for d in api.quotes(top)] == [
        ("EVIDENCE_PAPER_MISSING", pointer)
    ]
    passage = ("In every experiment, the forest lost less than one", "point of accuracy.")
    papers.add(DOI, 2, data=pdf(*[("Nothing.",)] * 5, passage))
    assert api.papers(top)[0].cached
    assert api.quotes(top) == ()
    papers.add(DOI, 2, data=pdf(*[("Nothing.",)] * 4, passage, ("Nothing.",)))
    assert [d.message.split("sought ")[1] for d in api.quotes(top)] == [
        "on page 6, as its location says"
    ]


# --- papers fetched ---


def answering(monkeypatch: pytest.MonkeyPatch, answers: Mapping[str, bytes]) -> list[str]:
    """Each URL `urllib` is asked for, in order, answered from `answers`: no test reaches the
    network."""
    asked: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        asked.append(request.full_url)
        return io.BytesIO(answers[request.full_url])

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return asked


def test_add_fetches_an_arxiv_doi_from_arxiv_at_its_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An arXiv DOI's paper is arXiv's, at the version the evidence gives, counted from 1."""
    asked = answering(monkeypatch, {"https://arxiv.org/pdf/1706.03762v5": PAPER})
    assert papers.add("10.48550/arXiv.1706.03762", 5) == 2
    assert asked == ["https://arxiv.org/pdf/1706.03762v5"]
    assert papers.get("10.48550/arXiv.1706.03762", 5) == PAPER
    assert papers.get("10.48550/arXiv.1706.03762", None) is None


def test_add_fetches_any_other_doi_through_unpaywall(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any other DOI's paper is the open-access PDF Unpaywall names as its best, asked with the
    user's email address."""
    record = f"https://api.unpaywall.org/v2/{DOI}?email=me%40example.org"
    best = "https://example.org/forests.pdf"
    found = json.dumps({"best_oa_location": {"url_for_pdf": best}}).encode()
    asked = answering(monkeypatch, {record: found, best: PAPER})
    assert papers.add(DOI, None, email="me@example.org") == 2
    assert asked == [record, best]
    assert papers.get(DOI, None) == PAPER


# --- astra paper ---


def astra(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


@pytest.fixture
def cited(tmp_path: Path) -> Path:
    """An analysis whose prior insight quotes page 2 of the work `DOI`, and `PAPER`'s file."""
    text = MINIMAL + "prior_insights:\n  noise:\n    claim: It resists noise.\n    evidence:\n"
    top = repository(tmp_path / "analysis", {"astra.yaml": text + evidence(cites(ACROSS))})
    (tmp_path / "paper.pdf").write_bytes(PAPER)
    return top


def test_add_file_keeps_a_paper_that_list_shows(cited: Path) -> None:
    before = astra("paper", "list", str(cited))
    assert before.exit_code == 0
    assert before.stdout == f"{DOI}: not in the cache: `astra paper add {DOI}`\n"
    added = astra("paper", "add", DOI, "--file", str(cited.parent / "paper.pdf"))
    assert added.exit_code == 0
    assert "2 page(s)" in added.stdout
    after = astra("paper", "list", str(cited))
    assert (after.exit_code, after.stdout) == (0, f"{DOI}: in the cache\n")


def test_verify_exits_0_whether_or_not_a_quote_is_found(cited: Path) -> None:
    """The warnings never change an exit code."""
    assert astra("paper", "add", DOI, "--file", str(cited.parent / "paper.pdf")).exit_code == 0
    found = astra("paper", "verify", str(cited))
    assert (found.exit_code, found.stdout.splitlines()[-1]) == (
        0,
        "No warnings: each quote cited by DOI is in its paper.",
    )
    (cited / "astra.yaml").write_text(
        (cited / "astra.yaml").read_text().replace("lost less than one point", "gained two points")
    )
    missing = astra("paper", "verify", str(cited))
    assert missing.exit_code == 0
    lines = missing.stdout.splitlines()
    assert lines[0] == "astra.yaml"
    assert lines[1].startswith("  12:42 warning EVIDENCE_QUOTE_NOT_FOUND the quote isn't found")


def test_verify_exits_1_for_an_invalid_analysis(cited: Path) -> None:
    """As for `plan`: no quotes are sought in an analysis that breaks a `MUST`."""
    (cited / "astra.yaml").write_text(MINIMAL.replace("type: metric", "type: plot"))
    result = astra("paper", "verify", str(cited))
    assert result.exit_code == 1
    assert "error INVALID_VALUE" in result.stdout


def test_seek_shows_the_pages_each_quote_given_is_on(cited: Path) -> None:
    """With no analysis, each quote is sought as `verify` seeks it, in the whole text, and shown
    with the pages it is on: alone, or across two."""
    assert astra("paper", "add", DOI, "--file", str(cited.parent / "paper.pdf")).exit_code == 0
    result = astra("paper", "seek", DOI, ACROSS, "noise", "held-out data.\nIn every experiment")
    assert (result.exit_code, result.stdout.splitlines()) == (
        0,
        [
            f"found on page 2: {ACROSS}",
            "found on pages 1 and 2: noise",
            "found across pages 1-2: held-out data. In every experiment",
        ],
    )


def test_seek_exits_1_when_a_quote_isnt_found(cited: Path) -> None:
    """Within --page, a quote is sought on that page alone, as within a location's `page=`."""
    assert astra("paper", "add", DOI, "--file", str(cited.parent / "paper.pdf")).exit_code == 0
    on_1 = astra("paper", "seek", DOI, ACROSS, "label noise", "--page", "1")
    assert (on_1.exit_code, on_1.stdout.splitlines()) == (
        1,
        [f"not found on page 1: {ACROSS}", "found on page 1: label noise"],
    )
    gained = "the forest gained two points of accuracy"
    whole = astra("paper", "seek", DOI, gained)
    assert (whole.exit_code, whole.stdout) == (1, f"not found in the whole text: {gained}\n")


def test_seek_needs_the_paper_in_the_cache_and_a_quote(cited: Path) -> None:
    missing = astra("paper", "seek", DOI, ACROSS)
    assert missing.exit_code == 2
    assert f"isn't in the cache: run `astra paper add {DOI}`" in missing.stderr
    assert astra("paper", "add", DOI, "--file", str(cited.parent / "paper.pdf")).exit_code == 0
    versioned = astra("paper", "seek", DOI, ACROSS, "--version", "2")
    assert versioned.exit_code == 2
    assert f"run `astra paper add {DOI} --version 2`" in versioned.stderr
    on_3 = astra("paper", "seek", DOI, ACROSS, "--page", "3")
    assert on_3.exit_code == 2 and "has 2 page(s), and no page 3" in on_3.stderr
    blank = astra("paper", "seek", DOI, ACROSS, " ")
    assert blank.exit_code == 2 and "a quote can't be blank" in blank.stderr
    assert astra("paper", "seek", DOI).exit_code == 2


def test_seek_names_two_pages_at_most() -> None:
    """A quote on no page alone is on each two pages it runs across, and on none named where it
    runs across more."""
    pages = ("It begins here, and the quote", "runs on", "to its end on page three.")
    assert quotes.seek("runs on", pages).pages == ((2, 2),)
    assert quotes.seek("the quote runs on", pages).pages == ((1, 2),)
    across = "the quote runs on to its end"
    assert quotes.seek(across, pages) == quotes.Sought(across, None, True, ())
    assert quotes.seek(across, pages, 2) == quotes.Sought(across, 2, False, ())


def test_api_seek_reads_the_paper_once_for_each_quote_given() -> None:
    """Each quote, in the order given, with no analysis: a quote is never read as its
    letters."""
    with pytest.raises(papers.PaperError, match=f"run `astra paper add {DOI}`"):
        api.seek(DOI, ACROSS)
    papers.add(DOI, None, data=PAPER)
    assert api.seek(DOI, ACROSS, "noise", "the forest gained two points") == (
        quotes.Sought(ACROSS, None, True, ((2, 2),)),
        quotes.Sought("noise", None, True, ((1, 1), (2, 2))),
        quotes.Sought("the forest gained two points", None, False, ()),
    )
    assert api.seek(DOI, ACROSS, page=1) == (quotes.Sought(ACROSS, 1, False, ()),)
    assert api.seek(DOI) == ()
    with pytest.raises(api.RequestError, match="has 2 page"):
        api.seek(DOI, ACROSS, page=3)


def test_add_refuses_what_isnt_a_pdf(cited: Path) -> None:
    (cited.parent / "paper.txt").write_text("not a paper\n")
    result = astra("paper", "add", DOI, "--file", str(cited.parent / "paper.txt"))
    assert result.exit_code == 2
    assert "isn't a PDF" in result.stderr
    assert "not in the cache" in astra("paper", "list", str(cited)).stdout


def test_add_fetches_only_what_it_can_without_more(cited: Path) -> None:
    """Unpaywall, which finds a DOI's open-access copy, asks for an email address, and knows
    no versions: neither is fetched, and nothing is asked of the network."""
    no_email = astra("paper", "add", DOI)
    assert no_email.exit_code == 2 and "--email" in no_email.stderr
    versioned = astra("paper", "add", DOI, "--version", "2", "--email", "me@example.org")
    assert versioned.exit_code == 2 and "only arXiv's papers" in versioned.stderr
