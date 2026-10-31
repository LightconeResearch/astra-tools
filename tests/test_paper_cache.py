"""Paper cache lookup and the metadata it stores."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra.papers.cache import PaperCache, normalize_doi
from astra.papers.download import plain_title


@pytest.mark.parametrize(
    "spelling",
    [
        "10.1088/0004-637X/712/1/260",
        "10.1088/0004-637x/712/1/260",
        "doi: 10.1088/0004-637X/712/1/260",
        "https://doi.org/10.1088/0004-637X/712/1/260",
        "http://dx.doi.org/10.1088/0004-637X/712/1/260",
    ],
)
def test_a_doi_has_one_key_however_it_is_spelled(spelling: str) -> None:
    assert normalize_doi(spelling) == "10.1088/0004-637x/712/1/260"


def test_a_paper_is_found_whatever_case_its_doi_is_asked_in(tmp_path: Path) -> None:
    cache = PaperCache(tmp_path)
    cache.add("10.1088/0004-637X/712/1/260", b"%PDF-1.4", title="GD-1")
    found = cache.get("https://doi.org/10.1088/0004-637x/712/1/260")
    assert found is not None
    assert found.metadata.title == "GD-1"
    assert cache.has("10.1088/0004-637x/712/1/260")


def test_a_differently_cased_add_reuses_the_entry(tmp_path: Path) -> None:
    cache = PaperCache(tmp_path)
    cache.add("10.1093/MNRAS/stv1198", b"%PDF-1.4")
    cache.add("10.1093/mnras/stv1198", b"%PDF-1.5")
    assert len(cache.list_papers()) == 1


def test_a_version_is_still_its_own_entry(tmp_path: Path) -> None:
    cache = PaperCache(tmp_path)
    cache.add("10.48550/arXiv.1706.03762", b"%PDF-1.4", version=7)
    assert cache.get("10.48550/arxiv.1706.03762", version=7) is not None
    assert cache.get("10.48550/arxiv.1706.03762") is None


def test_an_absent_paper_is_still_absent(tmp_path: Path) -> None:
    assert PaperCache(tmp_path).get("10.1/none") is None
    assert PaperCache(tmp_path / "missing").get("10.1/none") is None


def test_a_registered_title_keeps_only_its_words() -> None:
    assert plain_title("<tt>emcee</tt>\n                    : The MCMC Hammer") == (
        "emcee : The MCMC Hammer"
    )
    assert plain_title("H<sub>0</sub> &amp; the <i>Gaia</i> scale") == "H0 & the Gaia scale"
    assert plain_title("GAPS IN THE GD-1 STAR STREAM") == "GAPS IN THE GD-1 STAR STREAM"
