"""A commit as Annex B reads it, through `CommitReader` (design §4.3): each entry as the commit's
tree holds it and each file the blob git stores, a symlink never followed, and what its tree
tracks; and a submodule's URL resolved as git resolves it. A path through a gitlink at a commit,
and a commit fetched once and kept, are tested through §17's rules (`test_commits`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra.sources.git import Repository
from astra.sources.reader import CommitReader, Entry
from astra.sources.remote import Remotes, resolve
from tests.conftest import git, repository


@pytest.fixture(scope="module")
def tree(tmp_path_factory: pytest.TempPathFactory) -> tuple[CommitReader, Path]:
    """A commit with two files whose names differ in case, a symlink to one and to their
    folder, and a submodule; then the working tree changed after it."""
    library = repository(tmp_path_factory.mktemp("library"), {"astra.yaml": "x\n"})
    top = repository(tmp_path_factory.mktemp("tree"), {"data/a.csv": "1\n", "data/A.csv": "2\n"})
    (top / "link.csv").symlink_to("data/a.csv")
    (top / "linked").symlink_to("data")
    git(top, "submodule", "--quiet", "add", str(library), "library")
    repository(top, {})
    commit = git(top, "rev-parse", "HEAD").strip()
    (top / "data" / "a.csv").write_text("changed\n")
    (top / "data" / "new.csv").write_text("3\n")
    return CommitReader(Repository(top), commit, None, Remotes()), top


def test_a_path_names_the_entry_of_the_commits_tree(tree: tuple[CommitReader, Path]) -> None:
    """Annex B *What a path names*, *Bytes*: the commit's tree, not the working tree; names
    that differ in case are two paths."""
    reader, _ = tree
    assert reader.stat("data") == Entry("folder")
    assert (reader.read("data/a.csv"), reader.read("data/A.csv")) == (b"1\n", b"2\n")
    assert reader.stat("data/new.csv") is None
    assert reader.stat("") == Entry("folder")
    with pytest.raises(FileNotFoundError):
        reader.read("data")


def test_a_symlink_is_an_entry_and_is_never_followed(tree: tuple[CommitReader, Path]) -> None:
    """Annex B *Symlinks*: a symlink is neither a file nor a folder, and a path through one
    names nothing."""
    reader, _ = tree
    assert reader.stat("link.csv") == Entry("symlink", "data/a.csv")
    assert reader.stat("linked/a.csv") is None
    with pytest.raises(FileNotFoundError):
        reader.read("link.csv")


def test_tracked_is_in_the_commits_tree_through_no_gitlink(
    tree: tuple[CommitReader, Path],
) -> None:
    """Annex B *Tracked*: a file or a symlink of the commit's tree is tracked; one in a
    submodule isn't, nor one that isn't there."""
    reader, _ = tree
    paths = ["data/a.csv", "link.csv", "library/astra.yaml", "data/new.csv", "data"]
    assert reader.tracked("", paths) == {"data/a.csv", "link.csv"}


@pytest.mark.parametrize(
    ("base", "url", "resolved"),
    [
        (
            "https://example.org/group/project.git",
            "../library.git",
            "https://example.org/group/library.git",
        ),
        (
            "https://example.org/group/project.git/",
            "./library",
            "https://example.org/group/project.git/library",
        ),
        (
            "https://example.org/group/project",
            "../../other/library/",
            "https://example.org/other/library",
        ),
        (
            "git@example.org:group/project.git",
            "../library.git",
            "git@example.org:group/library.git",
        ),
        ("git@example.org:project.git", "../library.git", "git@example.org:library.git"),
        ("/srv/git/project", "../library", "/srv/git/library"),
        ("/srv/git/project", "https://example.org/library.git", "https://example.org/library.git"),
        ("/srv/git/project", "/srv/elsewhere/library", "/srv/elsewhere/library"),
    ],
)
def test_a_relative_submodule_url_resolves_as_git_resolves_it(
    base: str, url: str, resolved: str
) -> None:
    """Annex B *A gitlink's commit*: `./` and `../` against the superproject's remote, each
    `../` removing its last segment, or an scp-like remote's path after its `:`."""
    assert resolve(base, url) == resolved
