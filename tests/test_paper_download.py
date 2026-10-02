"""Tests for paper identifier normalization and download behavior."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from astra.cli import main
from astra.papers import cache as cache_module
from astra.papers import download as download_module
from astra.papers.download import PaperDownloadResult


@pytest.mark.parametrize(
    ("identifier", "arxiv_id"),
    [
        ("arXiv:1105.3470", "1105.3470"),
        ("1105.3470", "1105.3470"),
        ("https://arxiv.org/abs/1105.3470", "1105.3470"),
        ("hep-th/9901001", "hep-th/9901001"),
        ("arXiv:hep-th/9901001", "hep-th/9901001"),
        ("https://arxiv.org/abs/hep-th/9901001", "hep-th/9901001"),
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
