"""A runner's building blocks: what stops a run in a checkout (`records.uncommitted_changes`),
and landing what a run made in a checkout of its own in the main checkout (`records.land`), which
the main checkout's `check` then judges.

The stack is `test_validate`'s worked example, committed with its input and the script its first
recipe runs, and built as a runner builds it (`conftest.build`).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from astra import api
from astra.records import land, uncommitted_changes
from tests.conftest import MINIMAL, build, git, repository
from tests.test_check import UNCHANGED, statuses
from tests.test_validate import WORKED_EXAMPLE


@pytest.fixture(scope="module")
def committed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {
        "astra.yaml": WORKED_EXAMPLE,
        "data/input1.csv": "1\n",
        "src/output1.py": "print('output1')\n",
    }
    return repository(tmp_path_factory.mktemp("worked"), files)


@pytest.fixture
def main(committed: Path, tmp_path: Path) -> Path:
    """The main checkout: a copy of `committed` of the test's own."""
    return Path(shutil.copytree(committed, tmp_path / "main", symlinks=True))


def head(top: Path) -> str:
    return git(top, "rev-parse", "HEAD").strip()


def checkout(main: Path, commit: str, folder: Path | None = None) -> Path:
    """A checkout of `commit` of its own, as a runner makes for a run: a detached `git worktree
    add` in a new folder, beside `main` or in `folder`."""
    path = Path(tempfile.mkdtemp(prefix="run-", dir=folder or main.parent))
    git(main, "worktree", "add", "--quiet", "--detach", str(path), commit)
    return path


def commit_of(top: Path, record: str) -> str:
    return str(json.loads((top / record).read_text("utf-8"))["generated_by"]["commit"])


# --- uncommitted_changes: the runner's UNCOMMITTED_CHANGES ---


def test_the_records_and_results_of_a_run_dont_stop_it(main: Path) -> None:
    """A checkout whose only changes are the records and results of a run, each result's bytes
    the recorded ones, can run a recipe; so can one with no change."""
    assert uncommitted_changes(main) == ()
    build(main)
    assert uncommitted_changes(main) == ()


def test_the_records_and_results_of_any_run_dont_stop_it(main: Path) -> None:
    """The records and results of any run, not only those of the planned results: here of
    a universe that is gone, `u3`, and of an output that is gone, `old`, whose format holds a
    `.`; but not bytes at such a place that no valid record there gives."""
    build(main)
    records, results = main / ".astra" / "records", main / "results"
    for name, universe in (("output1", "u3"), ("old", None)):
        folder = () if universe is None else (universe,)
        source = records / "u1" / "output1.json"
        record = json.loads(source.read_text())
        record["address"] = "#".join((name, *folder))
        (records.joinpath(*folder)).mkdir(parents=True, exist_ok=True)
        records.joinpath(*folder, f"{name}.json").write_text(json.dumps(record))
        suffix = ".json" if universe else ".tar.gz"
        results.joinpath(*folder).mkdir(parents=True, exist_ok=True)
        shutil.copy(results / "u1" / "output1.json", results.joinpath(*folder, name + suffix))
    assert uncommitted_changes(main) == ()
    (results / "old.tar.gz").write_text("other\n")
    (main / "data" / "results").mkdir()
    (main / "data" / "results" / "x.csv").write_text("not an analysis's\n")
    assert uncommitted_changes(main) == ("data/results/x.csv", "results/old.tar.gz")


def test_a_change_outside_the_records_and_results_stops_a_run(main: Path) -> None:
    """What `git status` reports, staged or not, tracked or not."""
    build(main)
    (main / "src" / "output1.py").write_text("print('edited')\n")
    (main / "notes.txt").write_text("a note\n")
    (main / "data" / "input2.csv").write_text("2\n")
    git(main, "add", "data/input2.csv")
    found = uncommitted_changes(main)
    assert found == ("data/input2.csv", "notes.txt", "src/output1.py")


def test_bytes_that_arent_the_recorded_ones_stop_a_run(main: Path) -> None:
    """Each result's bytes the recorded ones, which a record that isn't valid gives none
    of; a record itself changes nothing a recipe reads, so a change at its place doesn't stop a
    run."""
    build(main)
    (main / "results" / "output2.csv").write_text("other\n")
    record = main / ".astra" / "records" / "u1" / "output1.json"
    record.write_text(json.dumps(json.loads(record.read_text())))
    assert uncommitted_changes(main) == ("results/output2.csv",)
    record.write_text("{}")
    found = uncommitted_changes(main)
    assert found == ("results/output2.csv", "results/u1/output1.json")


@pytest.fixture
def with_submodule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An analysis whose repository has a submodule, `sub`, of a local repository: git is let
    clone it from its path (`protocol.file.allow`)."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")
    sub = repository(tmp_path / "sub", {"a.csv": "1\n"})
    top = repository(tmp_path / "top", {"astra.yaml": MINIMAL})
    git(top, "submodule", "--quiet", "add", str(sub), "sub")
    git(top, "commit", "--quiet", "--message", "sub")
    return top


def test_a_change_in_a_submodule_stops_a_run(with_submodule: Path) -> None:
    """Submodules included: in the checkout and its submodules, each change inside one
    after its path; the submodule itself where its commit isn't the one the checkout's commit
    pins."""
    top = with_submodule
    assert uncommitted_changes(top) == ()
    (top / "sub" / "a.csv").write_text("2\n")
    (top / "sub" / "b.csv").write_text("3\n")
    assert uncommitted_changes(top) == ("sub/a.csv", "sub/b.csv")
    git(top / "sub", "commit", "--quiet", "--all", "--message", "a.csv")
    assert uncommitted_changes(top) == ("sub", "sub/b.csv")


# --- land, and the main checkout's check ---


def test_a_run_in_its_own_checkout_lands_its_results_in_the_main_one(main: Path) -> None:
    """A run in a checkout of its own makes the results there, while the main checkout is
    edited, which doesn't stop it; `land` moves them into the main checkout, whose `check`
    judges them unchanged and present, not committed until they are."""
    run = checkout(main, head(main))
    results = api.plan(run).results
    (main / "notes.txt").write_text("an agent keeps editing\n")
    assert uncommitted_changes(run) == ()
    build(run)
    assert uncommitted_changes(run) == ()
    assert {s[0] for s in statuses(api.check(main)).values()} == {"missing"}

    landed = land(run, main, results)
    assert [place.address for place in landed] == list(UNCHANGED)
    assert not (run / "results" / "output2.csv").exists()
    report = api.check(main)
    assert statuses(report) == UNCHANGED
    assert {s.committed for c in report.results for s in c.statuses} == {False}
    assert git(main, "status", "--porcelain", "--", "notes.txt") == "?? notes.txt\n"

    git(main, "add", ".astra", "results")
    git(main, "commit", "--quiet", "--message", "the records")
    report = api.check(main)
    assert statuses(report) == UNCHANGED
    assert {s.committed for c in report.results for s in c.statuses} == {True}


def test_land_moves_only_finished_results(main: Path) -> None:
    """A result is finished where its record is there and its bytes are the recorded ones;
    what isn't stays in the run's checkout."""
    run = checkout(main, head(main))
    results = api.plan(run).results
    build(run)
    (run / "results" / "output2.csv").write_text("other\n")
    (run / ".astra" / "records" / "u2" / "output1.json").unlink()
    assert [place.address for place in land(run, main, results)] == ["output1#u1"]
    assert not (main / "results" / "output2.csv").exists()
    assert (run / "results" / "output2.csv").exists()


def test_land_never_replaces_a_record_whose_commit_is_later_than_the_runs(main: Path) -> None:
    """A run from a later commit replaces the main checkout's records, and one from an earlier
    commit doesn't."""
    earlier = head(main)
    first, last = (checkout(main, earlier) for _ in range(2))
    later = head(repository(main, {"src/output1.py": "print('edited')\n"}))
    between = checkout(main, later)
    results = api.plan(main).results
    for run in (first, between, last):
        build(run)
    record = ".astra/records/output2.json"
    assert len(land(first, main, results)) == 3
    assert commit_of(main, record) == earlier
    assert len(land(between, main, results)) == 3
    assert commit_of(main, record) == later
    assert land(last, main, results) == ()
    assert commit_of(main, record) == later
    assert commit_of(last, record) == earlier


@pytest.fixture
def elsewhere(tmp_path: Path) -> Iterator[Path]:
    """A folder on another file system than the main checkout, as a run's checkout is where the
    project is on a scratch disk: a folder in /dev/shm, where that is one."""
    shm = Path("/dev/shm")
    if not os.access(shm, os.W_OK) or shm.stat().st_dev == tmp_path.stat().st_dev:
        pytest.skip("no other file system to put the run's checkout on")
    with tempfile.TemporaryDirectory(dir=shm) as folder:
        yield Path(folder)


def test_land_moves_results_from_another_file_system(main: Path, elsewhere: Path) -> None:
    """A run's checkout on another file system lands its results in the main checkout
    all the same, where `check` judges them."""
    run = checkout(main, head(main), elsewhere)
    results = api.plan(run).results
    build(run)
    assert [place.address for place in land(run, main, results)] == list(UNCHANGED)
    assert not (run / "results" / "output2.csv").exists()
    assert statuses(api.check(main)) == UNCHANGED
