"""The cache: one folder of plain files, `$ASTRA_CACHE_DIR` or the platform's user cache folder, a
relative `ASTRA_CACHE_DIR` refused, and entries put atomically."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from astra import cache
from astra.cli import main
from tests.conftest import MINIMAL, repository


def test_the_cache_is_astra_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTRA_CACHE_DIR", str(tmp_path / "cache"))
    assert cache.root() == tmp_path / "cache"


@pytest.mark.skipif(sys.platform in ("darwin", "win32"), reason="the XDG platforms' folder")
def test_by_default_the_cache_is_the_user_cache_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASTRA_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache.root() == tmp_path / "astra"
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert cache.root() == Path.home() / ".cache" / "astra"


def test_a_relative_astra_cache_dir_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It would put the cache inside whatever repository astra runs in: `validate` exits 2
    where it needs the cache."""
    monkeypatch.setenv("ASTRA_CACHE_DIR", "cache")
    with pytest.raises(cache.CacheError):
        cache.root()
    text = MINIMAL + f"analyses: {{up: {{url: 'file:///nowhere', commit: '{'0' * 40}'}}}}\n"
    result = CliRunner().invoke(main, ["validate", str(repository(tmp_path, {"astra.yaml": text}))])
    assert result.exit_code == 2
    assert "ASTRA_CACHE_DIR" in result.stderr


def test_a_value_put_is_got_until_another_replaces_it(tmp_path: Path) -> None:
    assert cache.get("validity", "key") is None
    cache.put("validity", "key", b"one")
    cache.put("validity", "other", b"two")
    assert (cache.get("validity", "key"), cache.get("validity", "other")) == (b"one", b"two")
    cache.put("validity", "key", b"three")
    assert cache.get("validity", "key") == b"three"
    assert len(list((cache.root() / "validity").iterdir())) == 2  # no temporary file is left
