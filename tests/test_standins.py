"""Stand-ins (§7, design §4.5): each built-in one recognised from what its
tool keeps in a file's place, committed in a real repository, and another package's, registered
in the entry-point group `astra.standins` (design §4.10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra import api
from astra.sources.git import Repository
from astra.sources.reader import WorktreeReader
from astra.sources.standins import BUILT_IN, Dvc, GitAnnex, GitLfs, registered
from tests.conftest import MINIMAL, repository

ANNEXED = "SHA256E-s6--" + "5" * 64 + ".bin"
"""A git-annex key: a SHA-256 backend, the size, the hash and the extension."""

LFS_POINTER = f"version https://git-lfs.github.com/spec/v1\noid sha256:{'a' * 64}\nsize 6\n"

DVC_FILE = "outs:\n- md5: 0cc175b9c0f1b6a831c399e269772661\n  size: 6\n  hash: md5\n  path: {}\n"


@pytest.fixture(scope="module")
def tree(tmp_path_factory: pytest.TempPathFactory) -> WorktreeReader:
    files = {
        "lfs.bin": LFS_POINTER,
        "lfs-no-size.bin": LFS_POINTER.replace("size 6\n", ""),
        "unlocked.bin": f"/annex/objects/{ANNEXED}\n",
        "plain.csv": "a,b\n1,2\n",
        "huge.csv.dvc": DVC_FILE.format("huge.csv"),
    }
    top = repository(tmp_path_factory.mktemp("tree"), {})
    (top / "locked.bin").symlink_to(f".git/annex/objects/Jx/3M/{ANNEXED}/{ANNEXED}")
    (top / "link.csv").symlink_to("plain.csv")
    repository(top, files)
    return WorktreeReader(top, Repository(top))


def test_git_lfs_recognises_its_pointer_file(tree: WorktreeReader) -> None:
    """design §4.5: `version`, then `oid sha256:…` and `size …`, at the path itself."""
    assert GitLfs().recognises(tree, "lfs.bin")
    assert GitLfs().place("lfs.bin") == "lfs.bin"
    assert not GitLfs().recognises(tree, "lfs-no-size.bin")
    assert not GitLfs().recognises(tree, "plain.csv")
    assert not GitLfs().recognises(tree, "nothere.bin")


def test_git_annex_recognises_a_symlink_or_a_pointer_into_its_objects(
    tree: WorktreeReader,
) -> None:
    """design §4.5: a locked file, committed as a symlink into `annex/objects/`, whose target
    needn't be there, and an unlocked pointer file; never another symlink or file."""
    assert GitAnnex().recognises(tree, "locked.bin")
    assert GitAnnex().recognises(tree, "unlocked.bin")
    assert not GitAnnex().recognises(tree, "link.csv")
    assert not GitAnnex().recognises(tree, "plain.csv")


def test_dvc_recognises_its_file_beside_the_path(tree: WorktreeReader) -> None:
    """design §4.5: `<path>.dvc` beside a path that names nothing, which is what git tracks."""
    assert Dvc().place("huge.csv") == "huge.csv.dvc"
    assert Dvc().recognises(tree, "huge.csv")
    assert not Dvc().recognises(tree, "plain.csv")


def test_each_gives_the_hash_and_size_of_what_it_stands_for_where_it_can(
    tree: WorktreeReader,
) -> None:
    """design §4.5's *Gives*, which the checker compares as an input's content (§20): a Git LFS
    pointer's `oid` and `size`, a git-annex key of a SHA-256 backend, and nothing of a DVC
    file, whose hash is an MD5."""
    assert GitLfs().gives(tree, "lfs.bin") == (f"sha256:{'a' * 64}", 6)
    assert GitLfs().gives(tree, "plain.csv") is None
    assert GitAnnex().gives(tree, "locked.bin") == (f"sha256:{'5' * 64}", 6)
    assert GitAnnex().gives(tree, "unlocked.bin") == (f"sha256:{'5' * 64}", 6)
    assert Dvc().gives(tree, "huge.csv") is None


PLUGIN = """\
from dataclasses import dataclass


@dataclass(frozen=True)
class Store:
    name: str = "store"

    def place(self, path):
        return path

    def recognises(self, reader, path):
        entry = reader.stat(path)
        return entry is not None and entry.kind == "symlink" and entry.target.startswith("store/")

    def gives(self, reader, path):
        return None


STANDIN = Store()
"""


def test_another_package_registers_a_stand_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """design §4.10: an object in the entry-point group `astra.standins` is recognised after the
    built-in ones, and keeps `MISSING_INPUT_FILE` for what it stands in for."""
    top = repository(tmp_path / "repo", {"store/x": "1\n"})
    (top / "data.raw").symlink_to("store/x")
    repository(top, {"astra.yaml": MINIMAL + "inputs:\n  raw: {path: data.raw}\n"})
    assert [d.code for d in api.validate(top).diagnostics] == ["MISSING_INPUT_FILE"]

    plugin = tmp_path / "plugin"
    (plugin / "astra_test_standin-0.dist-info").mkdir(parents=True)
    (plugin / "astra_test_standin.py").write_text(PLUGIN)
    (plugin / "astra_test_standin-0.dist-info" / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: astra-test-standin\nVersion: 0\n"
    )
    (plugin / "astra_test_standin-0.dist-info" / "entry_points.txt").write_text(
        "[astra.standins]\nstore = astra_test_standin:STANDIN\n"
    )
    monkeypatch.syspath_prepend(str(plugin))
    assert [standin.name for standin in registered()] == [
        *(standin.name for standin in BUILT_IN),
        "store",
    ]
    assert api.validate(top).diagnostics == ()
