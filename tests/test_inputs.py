"""Inputs: `MISSING_INPUT_FILE`, `INPUT_NOT_TRACKED`, `INPUT_IN_ANOTHER_ANALYSIS` and
`RESERVED_PATH`, each path read against git, and no `INPUT_NOT_TRACKED` where there is no file.

The breaking cases share one stack, each of whose inputs breaks one rule or two; the keeping
ones another, whose every input is one file, tracked, inside its own analysis: as a file, staged,
in a submodule analysis's own index, or through a stand-in."""

from __future__ import annotations

import pytest

from astra import api
from astra.rules import inputs
from tests.conftest import MINIMAL, git, repository
from tests.test_standins import ANNEXED, DVC_FILE


def reading(paths: dict[str, str], analyses: str = "{}") -> str:
    """An analysis whose inputs are `paths`, by id, and which declares `analyses`."""
    entries = "".join(f"  {id_}: {{path: '{path}'}}\n" for id_, path in paths.items())
    return f"{MINIMAL}analyses: {analyses}\ninputs:\n{entries}"


def found(report: api.ValidationReport, code: str) -> list[tuple[str, str]]:
    return [(d.location.file, d.location.pointer) for d in report.diagnostics if d.code == code]


@pytest.fixture(scope="module")
def broken(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    """A root whose inputs each break a rule, a declared analysis `sub` with one, and a
    submodule analysis `stage` whose input is tracked in no index but the root's."""
    data = repository(tmp_path_factory.mktemp("data"), {"x.csv": "1\n"})
    stage = repository(
        tmp_path_factory.mktemp("stage"), {"astra.yaml": reading({"own": "data/y.csv"})}
    )
    root = reading(
        {
            "gone": "data/gone.csv",
            "folder": "data",
            "linked": "link.csv",
            "through": "linked/a.csv",
            "module": "lib",
            "above": "../x.csv",
            "untracked": "data/new.csv",
            "ignored": "data/ignored.csv",
            "in_lib": "lib/x.csv",
            "dvc_untracked": "data/big.csv",
            "nested": "sub/data/x.csv",
            "kept_out": ".astra/records/x.json",
            "old_result": "results/old.csv",
            "theirs": "sub/results/x.csv",
        },
        "{sub: {path: sub}, old: {path: results/old}, hidden: {path: sub/.astra/hidden},"
        " stage: {path: stage}}",
    )
    files = {
        "astra.yaml": root,
        ".gitignore": "data/ignored.csv\n",
        "data/a.csv": "1\n",
        "data/ignored.csv": "1\n",
        "sub/astra.yaml": reading({"own": "results/y.csv"}),
        "sub/data/x.csv": "1\n",
        "sub/results/x.csv": "1\n",
        "sub/results/y.csv": "1\n",
        "sub/.astra/hidden/astra.yaml": MINIMAL,
        ".astra/records/x.json": "{}\n",
        "results/old.csv": "1\n",
        "results/old/astra.yaml": MINIMAL,
    }
    top = repository(tmp_path_factory.mktemp("broken"), files)
    (top / "link.csv").symlink_to("data/a.csv")
    (top / "linked").symlink_to("data")
    git(top, "submodule", "--quiet", "add", str(data), "lib")
    git(top, "submodule", "--quiet", "add", str(stage), "stage")
    repository(top, {})
    (top / "data" / "new.csv").write_text("1\n")
    (top / "data" / "big.csv.dvc").write_text(DVC_FILE.format("big.csv"))
    (top / "stage" / "data").mkdir()
    (top / "stage" / "data" / "y.csv").write_text("1\n")
    return api.validate(top)


def test_a_path_naming_no_file_breaks_missing_input_file(broken: api.ValidationReport) -> None:
    """Nothing there, a folder, a symlink (never followed, and no stand-in), a path through a
    symlinked folder, and a submodule's gitlink. A path above the top isn't checked by
    MISSING_INPUT_FILE."""
    assert found(broken, "MISSING_INPUT_FILE") == [
        ("astra.yaml", f"/inputs/{id_}/path")
        for id_ in ("gone", "folder", "linked", "through", "module")
    ]
    assert all(d.level == "error" for d in broken.diagnostics)


def test_a_file_not_in_the_index_breaks_input_not_tracked(broken: api.ValidationReport) -> None:
    """Untracked, ignored, inside a plain data submodule, or with a DVC stand-in that isn't
    tracked either; and in a submodule analysis, a file its own index lacks. No input that
    names no file is checked."""
    assert found(broken, "INPUT_NOT_TRACKED") == [
        *(
            ("astra.yaml", f"/inputs/{id_}/path")
            for id_ in ("untracked", "ignored", "in_lib", "dvc_untracked")
        ),
        ("stage/astra.yaml", "/inputs/own/path"),
    ]


def test_a_file_outside_its_analysis_breaks_input_in_another_analysis(
    broken: api.ValidationReport,
) -> None:
    """A file above the analysis's folder, and files inside `sub`, a folder below it that
    holds an astra.yaml file of its own. `above`, whose `..` has no segment before it, goes
    above the top, and so outside the analysis's folder."""
    assert found(broken, "INPUT_IN_ANOTHER_ANALYSIS") == [
        ("astra.yaml", f"/inputs/{id_}/path") for id_ in ("above", "nested", "theirs")
    ]
    message = next(d.message for d in broken.diagnostics if "/nested/" in d.location.pointer)
    assert "`sub`" in message


def test_a_path_in_a_runners_folder_breaks_reserved_path(broken: api.ValidationReport) -> None:
    """Inputs in the analysis's own `.astra/` and `results/`, and in `sub`'s; declarations inside
    the root's `results/` and `sub`'s `.astra/`; and `sub`'s own input in its `results/`."""
    assert found(broken, "RESERVED_PATH") == [
        ("astra.yaml", "/analyses/old/path"),
        ("astra.yaml", "/analyses/hidden/path"),
        *(("astra.yaml", f"/inputs/{id_}/path") for id_ in ("kept_out", "old_result", "theirs")),
        ("sub/astra.yaml", "/inputs/own/path"),
    ]
    old = next(d for d in broken.diagnostics if d.location.pointer == "/analyses/old/path")
    assert (old.location.line, old.location.column) == (8, 42)


@pytest.fixture(scope="module")
def kept(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    library = repository(
        tmp_path_factory.mktemp("library"),
        {"astra.yaml": reading({"own": "data/x.csv"}), "data/x.csv": "1\n"},
    )
    root = reading(
        {
            "input1": "data/input1.csv",
            "dotted": "./data/./input1.csv",
            "staged": "data/staged.csv",
            "plain": "notes/x.csv",
            "docs": "docs/results/x.csv",
            "near": "results2/x.csv",
            "annexed": "data/big.bin",
            "dvc": "data/huge.csv",
            "pulled": "data/pulled.csv",
        },
        "{lib: {path: lib}, sub: {path: sub}}",
    )
    files = {
        "astra.yaml": root,
        ".gitignore": "data/huge.csv\ndata/pulled.csv\n",
        "data/input1.csv": "1\n",
        "notes/x.csv": "1\n",
        "docs/results/x.csv": "1\n",
        "results2/x.csv": "1\n",
        "data/huge.csv.dvc": DVC_FILE.format("huge.csv"),
        "data/pulled.csv": "1\n",
        "data/pulled.csv.dvc": DVC_FILE.format("pulled.csv"),
        "sub/astra.yaml": reading({"own": "data/x.csv"}),
        "sub/data/x.csv": "1\n",
    }
    top = repository(tmp_path_factory.mktemp("kept"), {})
    (top / "data").mkdir()
    (top / "data" / "big.bin").symlink_to(f"../.git/annex/objects/Jx/3M/{ANNEXED}/{ANNEXED}")
    repository(top, files)
    git(top, "submodule", "--quiet", "add", str(library), "lib")
    repository(top, {})
    (top / "data" / "staged.csv").write_text("1\n")
    git(top, "add", "data/staged.csv")
    return api.validate(top)


def test_a_tracked_file_inside_its_analysis_keeps_every_rule(kept: api.ValidationReport) -> None:
    """A committed or staged file, tidied as text; outside every folder holding an astra.yaml
    (`notes`, `docs`), and outside every `results/` (`results2` isn't one); and a submodule
    analysis's input, tracked in its own index."""
    assert [d for d in kept.diagnostics if d.code in inputs.CODES] == []


def test_a_stand_in_keeps_missing_input_file_and_input_not_tracked(
    kept: api.ValidationReport,
) -> None:
    """A git-annex symlink into annex/objects/, committed; a DVC file beside a path that names
    nothing, or an ignored file. A Git LFS pointer is a file kept at the path, so it keeps both
    rules as any file does."""
    pointers = {f"/inputs/{id_}/path" for id_ in ("annexed", "dvc", "pulled")}
    assert not any(d.location.pointer in pointers for d in kept.diagnostics)
