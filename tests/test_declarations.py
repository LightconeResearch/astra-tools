"""§15 Declared analyses: `DECLARATION_OUTSIDE_REPOSITORY`, `MISSING_DECLARED_ANALYSIS` for
declarations by path, and `CLASHING_RESULT_NAME`, with Annex D cases 2 and 3 as they apply to
them."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra import api
from tests.conftest import MINIMAL, git, repository


def declaring(analyses: str, outputs: str = "result") -> str:
    """An analysis that declares `analyses` (a flow map), with one output `outputs`."""
    return MINIMAL.replace("  result:", f"  {outputs}:") + f"analyses: {analyses}\n"


def found(report: api.ValidationReport) -> list[tuple[str, str, str, str | None]]:
    return [
        (d.code, d.location.file, d.location.pointer, d.location.key) for d in report.diagnostics
    ]


# --- DECLARATION_OUTSIDE_REPOSITORY ---


@pytest.mark.parametrize("path", ["..", "../..", "sub/../..", "./../repo"])
def test_a_path_above_the_top_breaks_declaration_outside_repository(
    tmp_path: Path, path: str
) -> None:
    """§15 *A declaration by path*: tidied as text, it goes above the top of the root's working
    tree, whatever is on disk there. Annex D case 3: MISSING_DECLARED_ANALYSIS isn't checked."""
    top = repository(tmp_path / "repo", {"astra.yaml": declaring(f"{{up: {{path: '{path}'}}}}")})
    report = api.validate(top)
    assert found(report) == [
        ("DECLARATION_OUTSIDE_REPOSITORY", "astra.yaml", "/analyses/up/path", None)
    ]
    location = report.diagnostics[0].location
    assert (location.line, location.column) == (8, 23)


def test_a_path_inside_the_working_tree_keeps_it(tmp_path: Path) -> None:
    """§15: `stage`'s `..` reaches the root, and `../other` its sibling, both inside the root's
    working tree; `x/../stage` is `stage`."""
    stage = declaring("{parent: {path: ..}, other: {path: ../other}}", "stage_result")
    files = {
        "astra.yaml": declaring("{stage: {path: stage}, round: {path: x/../stage}}"),
        "stage/astra.yaml": stage,
        "other/astra.yaml": MINIMAL,
    }
    assert found(api.validate(repository(tmp_path, files))) == []


def test_the_top_is_the_root_working_trees_not_the_roots_folder(tmp_path: Path) -> None:
    """Annex B *The top*: from a root below the top, `..` stays inside; and from a declared
    analysis, a path above the top breaks the rule in its own file."""
    files = {
        "stage/astra.yaml": declaring("{parent: {path: ..}, inner: {path: inner}}"),
        "astra.yaml": MINIMAL,
        "stage/inner/astra.yaml": declaring("{grand: {path: ../../..}}"),
    }
    report = api.validate(repository(tmp_path, files) / "stage")
    assert found(report) == [
        ("DECLARATION_OUTSIDE_REPOSITORY", "stage/inner/astra.yaml", "/analyses/grand/path", None)
    ]


# --- MISSING_DECLARED_ANALYSIS ---


@pytest.fixture(scope="module")
def missing(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    """A root declaring a folder that isn't there, one with no astra.yaml, one whose astra.yaml
    is a symlink, a symlinked folder, and a folder and a submodule each holding an analysis."""
    library = repository(tmp_path_factory.mktemp("library"), {"astra.yaml": MINIMAL})
    analyses = (
        "{gone: {path: gone}, empty: {path: empty}, aliased: {path: aliased},"
        " linked: {path: linked}, sub: {path: sub}, library: {path: library}}"
    )
    files = {
        "astra.yaml": declaring(analyses),
        "empty/notes.txt": "no analysis here\n",
        "sub/astra.yaml": declaring("{nested: {path: nested}}", "sub_result"),
    }
    top = repository(tmp_path_factory.mktemp("repo"), files)
    (top / "aliased").mkdir()
    (top / "aliased" / "astra.yaml").symlink_to("../sub/astra.yaml")
    (top / "linked").symlink_to("sub")
    git(top, "submodule", "--quiet", "add", str(library), "library")
    return api.validate(top)


def test_a_folder_without_an_astra_yaml_file_breaks_missing_declared_analysis(
    missing: api.ValidationReport,
) -> None:
    """§15 *A declaration by path*, Annex B *Symlinks*: no folder, no astra.yaml in it, an
    astra.yaml that is a symlink, or a folder reached through one; in the root's file, and in
    `sub`'s for its `nested`."""
    assert found(missing) == [
        ("MISSING_DECLARED_ANALYSIS", "astra.yaml", "/analyses/gone/path", None),
        ("MISSING_DECLARED_ANALYSIS", "astra.yaml", "/analyses/empty/path", None),
        ("MISSING_DECLARED_ANALYSIS", "astra.yaml", "/analyses/aliased/path", None),
        ("MISSING_DECLARED_ANALYSIS", "astra.yaml", "/analyses/linked/path", None),
        ("MISSING_DECLARED_ANALYSIS", "sub/astra.yaml", "/analyses/nested/path", None),
    ]
    assert all(d.level == "error" for d in missing.diagnostics)


def test_a_folder_or_a_submodule_holding_an_astra_yaml_keeps_it(
    missing: api.ValidationReport,
) -> None:
    """§15: a declared analysis can be a git submodule, read as Annex B says."""
    assert not any("/sub/" in d.location.pointer for d in missing.diagnostics)
    assert not any("library" in d.location.pointer for d in missing.diagnostics)


def test_an_invalid_declared_file_is_there_and_its_declarations_arent_followed(
    tmp_path: Path,
) -> None:
    """Annex D case 2: `sub`'s file breaks a schema rule, which is reported; it isn't missing,
    and its own declaration of a folder that isn't there isn't checked."""
    files = {
        "astra.yaml": declaring("{sub: {path: sub}}"),
        "sub/astra.yaml": declaring("{gone: {path: gone}}", "sub_result") + "name: x\n",
    }
    report = api.validate(repository(tmp_path, files))
    assert found(report) == [("UNKNOWN_FIELD", "sub/astra.yaml", "", "name")]


# --- CLASHING_RESULT_NAME ---


def test_an_output_sharing_its_id_with_a_declaration_breaks_clashing_result_name(
    tmp_path: Path,
) -> None:
    """§15 *One analysis, however it is declared*: reported at the output, with the declaration
    as a related place, in whichever file of the stack has both."""
    files = {
        "astra.yaml": declaring("{sub: {path: sub}}", "sub"),
        "sub/astra.yaml": declaring("{parent: {path: ..}}", "parent"),
    }
    report = api.validate(repository(tmp_path, files))
    assert found(report) == [
        ("CLASHING_RESULT_NAME", "astra.yaml", "/outputs", "sub"),
        ("CLASHING_RESULT_NAME", "sub/astra.yaml", "/outputs", "parent"),
    ]
    related = report.diagnostics[0].related
    assert [(r.file, r.pointer, r.key, r.line) for r in related] == [
        ("astra.yaml", "/analyses", "sub", 8)
    ]


def test_ids_of_other_kinds_may_be_the_same(tmp_path: Path) -> None:
    """§6 *Ids and maps*: only an input and an output, and an output and a declaration, never
    share an id; a decision may share one with a declaration."""
    text = declaring("{sub: {path: sub}}") + "decisions:\n  sub:\n    options: {a: {}}\n"
    files = {"astra.yaml": text, "sub/astra.yaml": MINIMAL}
    assert found(api.validate(repository(tmp_path, files))) == []
