"""Paths tidied as text, and the working tree as Annex B reads it. What `stat` finds at a path,
a symlink never followed, is tested through §7's rules (`test_inputs`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra.sources.git import Repository
from astra.sources.paths import join, lies_inside
from astra.sources.reader import WorktreeReader
from tests.conftest import repository


@pytest.mark.parametrize(
    ("folder", "path", "tidied"),
    [
        ("", "./data.csv", "data.csv"),
        ("", "subanalysis/", "subanalysis"),
        ("", "subanalysis/../data", "data"),
        ("stage", "../data//input1.csv", "data/input1.csv"),
        ("stage", "..", ""),
        ("", ".", ""),
    ],
)
def test_a_path_is_joined_to_its_folder_and_tidied_as_text(
    folder: str, path: str, tidied: str
) -> None:
    """Annex B *Tidying*: empty and `.` segments are dropped, and each `..` removes the segment
    before it."""
    assert join(folder, path) == tidied


@pytest.mark.parametrize(("folder", "path"), [("", ".."), ("stage", "../.."), ("", "a/../..")])
def test_a_path_that_goes_above_the_top_has_no_tidied_form(folder: str, path: str) -> None:
    """Annex B *The top*."""
    assert join(folder, path) is None


def test_lies_inside() -> None:
    """Annex B *Lies inside*: the folder's segments begin the path's, and the path has more."""
    assert lies_inside("results/u1/output1.csv", "results")
    assert not lies_inside("results2/x.csv", "results")
    assert not lies_inside("results", "results")
    assert lies_inside("stage/results", "stage")
    assert lies_inside("results", "")


def test_two_names_that_differ_in_case_are_two_paths(tmp_path: Path) -> None:
    """Annex B *What a path names*: `data/A.csv` and `data/a.csv` name two files."""
    top = repository(tmp_path, {"data/a.csv": "1\n", "data/A.csv": "2\n"})
    tree = WorktreeReader(top, Repository(top))
    assert tree.read("data/A.csv") != tree.read("data/a.csv")


def test_a_reader_reads_on_disk_whatever_git_holds(tmp_path: Path) -> None:
    """Annex B *Bytes*: in the working tree, a file is read from disk, committed or not."""
    top = repository(tmp_path, {"astra.yaml": "old"})
    (top / "astra.yaml").write_text("new")
    assert WorktreeReader(top, Repository(top)).read("astra.yaml") == b"new"
