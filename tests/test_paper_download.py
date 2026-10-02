"""Tests for paper identifier normalization and download behavior."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from click.testing import CliRunner

from astra.cli import main
from astra.papers import cache as cache_module
from astra.papers import download as download_module
from astra.papers.download import DOIMetadata, PaperDownloadResult


@pytest.fixture
def mock_http_transport(monkeypatch: pytest.MonkeyPatch):
    clients: list[httpx.Client] = []

    def install(handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        monkeypatch.setattr(download_module, "httpx", httpx)
        monkeypatch.setattr(httpx, "get", client.get)
        clients.append(client)

    yield install

    for client in clients:
        client.close()


@pytest.mark.parametrize(
    ("identifier", "arxiv_id"),
    [
        ("arXiv:1105.3470", "1105.3470"),
        ("1105.3470", "1105.3470"),
        ("https://arxiv.org/abs/1105.3470", "1105.3470"),
        ("hep-th/9901001", "hep-th/9901001"),
        ("arXiv:hep-th/9901001", "hep-th/9901001"),
        ("https://arxiv.org/abs/hep-th/9901001", "hep-th/9901001"),
        ("https://arxiv.org/pdf/1105.3470v2.pdf", "1105.3470v2"),
        ("https://arxiv.org/pdf/1105.3470", "1105.3470"),
        ("10.48550/arxiv.1105.3470", "1105.3470"),
    ],
)
def test_download_paper_normalizes_arxiv_identifier_forms(
    monkeypatch: pytest.MonkeyPatch, identifier: str, arxiv_id: str
) -> None:
    calls: list[tuple[str, str, int | None]] = []

    def download_arxiv(arxiv_id: str, doi: str, version: int | None) -> PaperDownloadResult:
        calls.append((arxiv_id, doi, version))
        return PaperDownloadResult(success=True)

    monkeypatch.setattr(download_module, "_download_arxiv_pdf", download_arxiv)
    monkeypatch.setattr(
        download_module,
        "_try_unpaywall",
        lambda doi: pytest.fail(f"arXiv identifier routed to Unpaywall: {doi}"),
    )

    download_module.download_paper(identifier)

    assert calls == [(arxiv_id, f"10.48550/arXiv.{arxiv_id}", None)]


def test_paper_add_uses_canonical_doi_for_cache_and_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_doi = "10.48550/arXiv.1105.3470"
    calls: dict[str, str] = {}

    class RecordingCache:
        def __init__(self) -> None:
            pass

        def has(self, doi: str, version: int | None) -> bool:
            calls["cache_lookup"] = doi
            return False

        def add(self, **kwargs: object) -> SimpleNamespace:
            calls["cache_add"] = str(kwargs["doi"])
            return SimpleNamespace(
                metadata=SimpleNamespace(sha256="a" * 64, title=None),
                pdf_path=Path("paper.pdf"),
            )

    def download(doi: str, version: int | None) -> PaperDownloadResult:
        calls["download"] = doi
        return PaperDownloadResult(
            success=True,
            content=b"%PDF-1.4\n",
            url="https://arxiv.org/pdf/1105.3470.pdf",
        )

    monkeypatch.setattr(cache_module, "PaperCache", RecordingCache)
    monkeypatch.setattr(download_module, "download_paper", download)

    result = CliRunner().invoke(main, ["paper", "add", "arXiv:1105.3470"])

    assert result.exit_code == 0
    assert calls == {
        "cache_lookup": expected_doi,
        "download": expected_doi,
        "cache_add": expected_doi,
    }
    assert expected_doi in result.output


def test_unpaywall_not_found_explains_accepted_identifier_forms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock(status_code=404)
    mock_httpx = MagicMock()
    mock_httpx.get.return_value = response
    monkeypatch.setattr(download_module, "httpx", mock_httpx)

    result = download_module._try_unpaywall("not-a-doi")

    assert result.error is not None
    assert "arXiv:<id>" in result.error
    assert "bare arXiv ID" in result.error
    assert "https://arxiv.org/abs/<id>" in result.error


@pytest.mark.parametrize("status_code", [406, 429, 503])
def test_arxiv_pdf_retries_transient_statuses(
    monkeypatch: pytest.MonkeyPatch, mock_http_transport, status_code: int
) -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(status_code)
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4\\n",
        )

    mock_http_transport(handler)
    monkeypatch.setattr(download_module.time, "sleep", delays.append)
    monkeypatch.setattr(download_module, "fetch_doi_metadata", lambda doi: DOIMetadata())

    result = download_module._download_arxiv_pdf("1706.03762", "10.48550/arXiv.1706.03762")

    assert result.success is True
    assert calls == 2
    assert delays == [download_module._ARXIV_RETRY_BACKOFF]


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError],
    ids=["connect", "read-reset", "protocol"],
)
def test_arxiv_pdf_retries_connection_errors(
    monkeypatch: pytest.MonkeyPatch, mock_http_transport, error: type[httpx.TransportError]
) -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise error("connection dropped", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4\\n",
        )

    mock_http_transport(handler)
    monkeypatch.setattr(download_module.time, "sleep", delays.append)
    monkeypatch.setattr(download_module, "fetch_doi_metadata", lambda doi: DOIMetadata())

    result = download_module._download_arxiv_pdf("1706.03762", "10.48550/arXiv.1706.03762")

    assert result.success is True
    assert calls == 2
    assert delays == [download_module._ARXIV_RETRY_BACKOFF]


def test_arxiv_pdf_falls_back_to_export_host(
    monkeypatch: pytest.MonkeyPatch, mock_http_transport
) -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == "arxiv.org":
            return httpx.Response(406)
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4\\n",
        )

    mock_http_transport(handler)
    monkeypatch.setattr(download_module.time, "sleep", lambda delay: None)
    monkeypatch.setattr(download_module, "fetch_doi_metadata", lambda doi: DOIMetadata())

    result = download_module._download_arxiv_pdf("1706.03762", "10.48550/arXiv.1706.03762")

    assert result.success is True
    assert result.url == "https://export.arxiv.org/pdf/1706.03762.pdf"
    assert hosts == ["arxiv.org"] * download_module._ARXIV_MAX_ATTEMPTS + ["export.arxiv.org"]


def test_doi_metadata_failure_warns_without_failing_pdf_download(
    caplog, mock_http_transport
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "doi.org":
            return httpx.Response(503)
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4\\n",
        )

    mock_http_transport(handler)

    result = download_module._download_arxiv_pdf("1706.03762", "10.48550/arXiv.1706.03762")

    assert result.success is True
    assert "metadata lookup failed" in caplog.text.lower()
    assert "503" in caplog.text


def test_cache_keys_arxiv_identifier_forms_by_their_doi(tmp_path: Path) -> None:
    cache = cache_module.PaperCache(tmp_path)
    cache.add("arXiv:1105.3470", b"%PDF-1.4\n")

    for identifier in ("10.48550/arXiv.1105.3470", "1105.3470", "https://arxiv.org/abs/1105.3470"):
        cached = cache.get(identifier)
        assert cached is not None
        assert cached.metadata.doi == "10.48550/arXiv.1105.3470"
    assert cache.remove("arXiv:1105.3470")
    assert not cache.has("10.48550/arXiv.1105.3470")


@pytest.mark.parametrize("doi", ["10.1038/s41586-023-06221-2", "10.1234/hep-th/9901001x"])
def test_normalize_leaves_other_dois_alone(doi: str) -> None:
    assert download_module.normalize_arxiv_identifier(doi) == doi
