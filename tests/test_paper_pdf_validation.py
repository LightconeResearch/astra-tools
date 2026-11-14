"""Tests for PDF validation before caching (issue #48).

Ensures that non-PDF content (HTML paywall pages, CAPTCHA redirects, etc.)
is rejected before being written to the paper cache.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from astra.papers.cache import PaperCache
from astra.papers.download import is_valid_pdf

# ---------------------------------------------------------------------------
# is_valid_pdf helper
# ---------------------------------------------------------------------------

PDF_MAGIC = b"%PDF-1.4\n%some content"
HTML_CONTENT = b"<!DOCTYPE html><html><body>Please enable cookies</body></html>"
EMPTY_CONTENT = b""


class TestIsValidPdf:
    def test_valid_pdf_magic_bytes(self) -> None:
        assert is_valid_pdf(PDF_MAGIC) is True

    def test_html_content_rejected(self) -> None:
        assert is_valid_pdf(HTML_CONTENT) is False

    def test_empty_content_rejected(self) -> None:
        assert is_valid_pdf(EMPTY_CONTENT) is False

    def test_short_content_rejected(self) -> None:
        assert is_valid_pdf(b"%PD") is False

    def test_exact_magic_bytes(self) -> None:
        assert is_valid_pdf(b"%PDF") is True

    def test_json_content_rejected(self) -> None:
        assert is_valid_pdf(b'{"error": "not found"}') is False


# ---------------------------------------------------------------------------
# PaperCache.add() guard
# ---------------------------------------------------------------------------


class TestPaperCacheAddValidation:
    def test_add_rejects_non_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = PaperCache(Path(tmp))
            with pytest.raises(ValueError, match="not a valid PDF"):
                cache.add(
                    doi="10.1234/test",
                    pdf_content=HTML_CONTENT,
                )

    def test_add_rejects_empty_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = PaperCache(Path(tmp))
            with pytest.raises(ValueError, match="not a valid PDF"):
                cache.add(
                    doi="10.1234/test",
                    pdf_content=EMPTY_CONTENT,
                )

    def test_add_accepts_valid_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = PaperCache(Path(tmp))
            cached = cache.add(
                doi="10.1234/test",
                pdf_content=PDF_MAGIC,
                title="Test Paper",
            )
            assert cached.pdf_path.exists()
            assert cached.pdf_path.read_bytes() == PDF_MAGIC

    def test_add_from_file_rejects_non_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html_file = tmp_path / "fake.pdf"
            html_file.write_bytes(HTML_CONTENT)

            cache = PaperCache(tmp_path / "cache")
            with pytest.raises(ValueError, match="not a valid PDF"):
                cache.add_from_file(doi="10.1234/test", pdf_path=html_file)

    def test_add_from_file_accepts_valid_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_file = tmp_path / "paper.pdf"
            pdf_file.write_bytes(PDF_MAGIC)

            cache = PaperCache(tmp_path / "cache")
            cached = cache.add_from_file(doi="10.1234/test", pdf_path=pdf_file)
            assert cached.pdf_path.exists()


# ---------------------------------------------------------------------------
# Download path validation (mocked HTTP)
# ---------------------------------------------------------------------------


class TestUnpaywallPdfValidation:
    """Ensure _try_unpaywall rejects non-PDF download responses."""

    def _make_response(self, content: bytes, content_type: str = "text/html") -> MagicMock:
        resp = MagicMock()
        resp.content = content
        resp.headers = {"content-type": content_type}
        resp.raise_for_status = MagicMock()
        return resp

    def _make_unpaywall_api_response(self, pdf_url: str) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "title": "Test Paper",
            "best_oa_location": {"url_for_pdf": pdf_url},
            "z_authors": [],
        }
        return resp

    def test_unpaywall_rejects_html_response(self) -> None:
        from astra.papers.download import _try_unpaywall

        api_resp = self._make_unpaywall_api_response("https://example.com/paper.pdf")
        pdf_resp = self._make_response(HTML_CONTENT, "text/html")

        with patch("astra.papers.download.httpx") as mock_httpx:
            mock_httpx.get.side_effect = [api_resp, pdf_resp]
            mock_httpx.HTTPStatusError = Exception
            mock_httpx.RequestError = Exception

            result = _try_unpaywall("10.1234/fake")

        assert result.success is False
        assert "not a valid PDF" in result.error  # type: ignore[operator]
        assert "paywall" in result.error.lower()  # type: ignore[operator]

    def test_unpaywall_accepts_pdf_response(self) -> None:
        from astra.papers.download import _try_unpaywall

        api_resp = self._make_unpaywall_api_response("https://example.com/paper.pdf")
        pdf_resp = self._make_response(PDF_MAGIC, "application/pdf")

        with patch("astra.papers.download.httpx") as mock_httpx:
            mock_httpx.get.side_effect = [api_resp, pdf_resp]
            mock_httpx.HTTPStatusError = Exception
            mock_httpx.RequestError = Exception

            result = _try_unpaywall("10.1234/fake")

        assert result.success is True
        assert result.content == PDF_MAGIC


class TestArxivPdfValidation:
    """Ensure _download_arxiv_pdf rejects non-PDF magic bytes even with correct content-type."""

    def _make_arxiv_response(self, content: bytes, content_type: str) -> MagicMock:
        resp = MagicMock()
        resp.content = content
        resp.headers = {"content-type": content_type}
        resp.raise_for_status = MagicMock()
        return resp

    def test_arxiv_rejects_html_despite_pdf_content_type(self) -> None:
        from astra.papers.download import _download_arxiv_pdf

        resp = self._make_arxiv_response(HTML_CONTENT, "application/pdf")

        with patch("astra.papers.download.httpx") as mock_httpx:
            mock_httpx.get.return_value = resp
            mock_httpx.HTTPStatusError = Exception
            mock_httpx.RequestError = Exception

            result = _download_arxiv_pdf("1706.03762", "10.48550/arXiv.1706.03762")

        assert result.success is False
        assert "magic bytes" in result.error  # type: ignore[operator]

    def test_arxiv_accepts_valid_pdf(self) -> None:
        from astra.papers.download import _download_arxiv_pdf

        resp = self._make_arxiv_response(PDF_MAGIC, "application/pdf")

        with (
            patch("astra.papers.download.httpx") as mock_httpx,
            patch("astra.papers.download.fetch_doi_metadata") as mock_meta,
        ):
            mock_httpx.get.return_value = resp
            mock_httpx.HTTPStatusError = Exception
            mock_httpx.RequestError = Exception
            mock_meta.return_value = MagicMock(title="Attention Is All You Need", authors=[])

            result = _download_arxiv_pdf("1706.03762", "10.48550/arXiv.1706.03762")

        assert result.success is True
        assert result.content == PDF_MAGIC
