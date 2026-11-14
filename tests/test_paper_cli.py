"""The `astra paper` commands, as astra-tools 0.2 had them: a paper kept from a local PDF is
listed, shown, found by its path, and its quotes verified from JSON on stdin."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra.cli import main

DOI = "10.9999/example"
TEXT = "Robust estimators reduce the influence of outliers on fitted relations."


def pdf(text: str) -> bytes:
    """A one-page PDF whose text is `text`."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    data += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    data += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return data


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home of its own, so the paper cache is empty."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path


def astra(*args: str, stdin: str | None = None) -> Result:
    return CliRunner().invoke(main, list(args), input=stdin)


def test_a_paper_added_from_a_pdf_is_listed_shown_and_found(home: Path) -> None:
    source = home / "paper.pdf"
    source.write_bytes(pdf(TEXT))
    assert astra("paper", "list").stdout.strip() == "No papers cached"
    added = astra("paper", "add", DOI, "-v", "2", "--pdf", str(source))
    assert added.exit_code == 0 and "Paper added to cache" in added.stdout
    assert (
        "already cached"
        in astra("paper", "add", DOI, "--version", "2", "--pdf", str(source)).stdout
    )
    path = astra("paper", "path", DOI, "-v", "2")
    assert path.exit_code == 0
    kept = Path(path.stdout.strip())
    assert kept.suffix == ".pdf" and kept.read_bytes() == source.read_bytes()
    assert DOI in astra("paper", "list").stdout
    shown = astra("paper", "show", DOI, "--version", "2")
    assert shown.exit_code == 0 and "SHA-256:" in shown.stdout
    assert astra("paper", "remove", DOI, "-v", "2").exit_code == 0
    assert astra("paper", "path", DOI, "-v", "2").exit_code == 1
    assert astra("paper", "show", DOI).exit_code == 1


def test_verify_quotes_reads_json_on_stdin_and_writes_json(home: Path) -> None:
    source = home / "paper.pdf"
    source.write_bytes(pdf(TEXT))
    assert astra("paper", "add", DOI, "--pdf", str(source)).exit_code == 0
    quotes = {"quotes": [{"text": "reduce the influence of outliers", "page": 1}]}
    result = astra("paper", "verify-quotes", DOI, stdin=json.dumps(quotes))
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["summary"] == {"total": 1, "verified": 1, "not_found": 0, "errors": 0}
    assert (output["results"][0]["status"], output["results"][0]["found_pages"]) == (
        "verified",
        [1],
    )
    quotes["quotes"].append({"text": "a sentence the paper never says anywhere at all"})
    result = astra("paper", "verify-quotes", DOI, stdin=json.dumps(quotes))
    assert result.exit_code == 1
    assert json.loads(result.stdout)["summary"]["not_found"] == 1
    one = astra("paper", "verify-quote", DOI, "-q", "influence of outliers", "--json")
    assert one.exit_code == 0 and json.loads(one.stdout)["status"] == "verified"


def test_verify_quotes_no_input(home: Path) -> None:
    result = astra("paper", "verify-quotes", "10.1234/test", stdin="")
    assert result.exit_code == 2
    assert "No input" in json.loads(result.stdout)["error"]


def test_verify_quotes_invalid_json(home: Path) -> None:
    result = astra("paper", "verify-quotes", "10.1234/test", stdin="not valid json{")
    assert result.exit_code == 2
    assert "Invalid JSON" in json.loads(result.stdout)["error"]


def test_verify_quotes_paper_not_cached(home: Path) -> None:
    quotes = json.dumps({"quotes": [{"text": "some quote"}]})
    result = astra("paper", "verify-quotes", "10.9999/test", "--version", "1", stdin=quotes)
    assert result.exit_code == 2
    output = json.loads(result.stdout)
    assert (output["doi"], output["version"]) == ("10.9999/test", 1)
    assert "not in cache" in output["error"] and "summary" in output
