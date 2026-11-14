"""Analyses from another commit or repository: `COMMIT_NOT_FOUND`, `COMMIT_NOT_ANCESTOR`,
`REMOTE_UNREACHABLE` and `DECLARED_ANALYSIS_INVALID`; `MISSING_DECLARED_ANALYSIS`,
`DECLARATION_OUTSIDE_REPOSITORY`, `RESERVED_PATH` and `INPUT_NOT_TRACKED` where they meet a
commit; identity, gitlinks crossed at a commit, and what a declaration that can't be read leaves
unchecked. Another local repository, reached by a `file://` URL, stands for a remote."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from astra import api
from astra.cli import main
from tests.conftest import MINIMAL, git, repository

NOWHERE = "file:///nowhere/at/all.git"
"""A remote no commit can be got from."""

ZERO = "0" * 40
"""A full commit id that no repository has."""


def declaring(analyses: str, reads: str | None = None) -> str:
    """An analysis that declares `analyses` (a flow map), whose output reads `reads` (a flow
    list) if given."""
    text = (
        MINIMAL
        if reads is None
        else MINIMAL.replace("    recipe:", f"    inputs: {reads}\n    recipe:")
    )
    return text + f"analyses: {analyses}\n"


def reading(paths: dict[str, str]) -> str:
    """An analysis with an input at each path, by id."""
    inputs = ", ".join(f"{id_}: {{path: {path}}}" for id_, path in paths.items())
    return MINIMAL + f"inputs: {{{inputs}}}\n"


UNRESOLVED = MINIMAL.replace("    recipe:", "    inputs: [nothing]\n    recipe:")
"""An analysis whose output reads an address that names nothing."""


def commit(top: Path, files: dict[str, str | bytes], remove: tuple[str, ...] = ()) -> str:
    """Commit `files`, less `remove`, in the repository at `top`, and give the commit's id."""
    for path in remove:
        (top / path).unlink()
    repository(top, files)
    return git(top, "rev-parse", "HEAD").strip()


def found(report: api.ValidationReport) -> set[tuple[str, str, str, str | None]]:
    return {
        (d.code, d.location.file, d.location.pointer, d.location.commit) for d in report.diagnostics
    }


@pytest.fixture(scope="module")
def shared_cache(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A cache for the reports the module's fixtures share, outside every repository."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("ASTRA_CACHE_DIR", str(tmp_path_factory.mktemp("cache")))
        yield


# --- from a remote: REMOTE_UNREACHABLE, DECLARED_ANALYSIS_INVALID, MISSING_DECLARED_ANALYSIS ---


@pytest.fixture(scope="module")
def upstream(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """A repository of its own, with a commit for each case, by name, and its `url`."""
    top = tmp_path_factory.mktemp("upstream")
    commits = {"url": top.as_uri()}
    commits["valid"] = commit(
        top, {"astra.yaml": reading({"input1": "data/input1.csv"}), "data/input1.csv": "1\n"}
    )
    commits["older"] = commit(
        top, {"astra.yaml": declaring(f"{{before: {{path: ., commit: '{commits['valid']}'}}}}")}
    )
    commits["unresolved"] = commit(top, {"astra.yaml": UNRESOLVED})
    commits["unsupported"] = commit(top, {"astra.yaml": MINIMAL.replace("0.1.0", "0.2.0")})
    commits["schema"] = commit(top, {"astra.yaml": MINIMAL + "name: x\n"})
    commits["staged"] = commit(
        top, {"astra.yaml": declaring("{stage: {path: stage}}"), "stage/astra.yaml": UNRESOLVED}
    )
    commits["wrong"] = commit(
        top, {"astra.yaml": declaring(f"{{before: {{path: ., commit: '{ZERO}'}}}}")}
    )
    commits["empty"] = commit(top, {"notes.txt": "no analysis\n"}, remove=("astra.yaml",))
    return commits


@pytest.fixture(scope="module")
def broken(
    shared_cache: None, upstream: dict[str, str], tmp_path_factory: pytest.TempPathFactory
) -> api.ValidationReport:
    """A root declaring a commit of `upstream` for each way of breaking a rule, and commits that
    can't be got, with addresses through them."""
    url = upstream["url"]
    names = ("unresolved", "unsupported", "schema", "staged", "wrong", "empty")
    analyses = [f"{name}: {{url: '{url}', commit: '{upstream[name]}'}}" for name in names]
    analyses += [
        f"gone: {{url: '{NOWHERE}', commit: '{ZERO}'}}",
        f"twice: {{url: '{NOWHERE}', commit: '{ZERO}'}}",
        f"unknown: {{url: '{url}', commit: '{ZERO}'}}",
    ]
    text = declaring("{" + ", ".join(analyses) + "}", "[gone.result, unknown.result, empty.x]")
    return api.validate(repository(tmp_path_factory.mktemp("root"), {"astra.yaml": text}))


def test_a_commit_that_cant_be_got_breaks_remote_unreachable(
    broken: api.ValidationReport,
) -> None:
    """A URL nothing answers at, a commit the remote hasn't, and two declarations of one commit,
    each reported once; and a `path` with a `commit` in a file read from a remote, got from that
    remote (`wrong`'s, further in). None is checked by MISSING_DECLARED_ANALYSIS or
    DECLARED_ANALYSIS_INVALID, and no address through them by UNRESOLVED_ADDRESS."""
    unreachable = {item for item in found(broken) if item[0] == "REMOTE_UNREACHABLE"}
    assert unreachable == {
        ("REMOTE_UNREACHABLE", "astra.yaml", f"/analyses/{name}", None)
        for name in ("gone", "twice", "unknown", "wrong")
    }
    assert not any(
        "/gone" in item[2] or "/unknown" in item[2] for item in found(broken) - unreachable
    )


def test_a_must_broken_at_a_commit_is_reported_twice(
    broken: api.ValidationReport, upstream: dict[str, str]
) -> None:
    """DECLARED_ANALYSIS_INVALID on the declaration, and the rule's own code at its place in the
    commit's file, with the commit and the URL; a schema rule too, and one broken in an analysis
    it declares."""
    for name in ("unresolved", "schema", "staged"):
        assert ("DECLARED_ANALYSIS_INVALID", "astra.yaml", f"/analyses/{name}", None) in found(
            broken
        )
    inside = {item for item in found(broken) if item[3] is not None}
    assert inside >= {
        ("UNRESOLVED_ADDRESS", "astra.yaml", "/outputs/result/inputs/0", upstream["unresolved"]),
        ("UNKNOWN_FIELD", "astra.yaml", "", upstream["schema"]),
        ("UNRESOLVED_ADDRESS", "stage/astra.yaml", "/outputs/result/inputs/0", upstream["staged"]),
    }
    (invalid,) = [d for d in broken.diagnostics if d.location.pointer == "/analyses/unresolved"]
    (there,) = [d for d in broken.diagnostics if d.location.commit == upstream["unresolved"]]
    assert invalid.level == "error" and invalid.related == (there.location,)
    assert there.location.url == upstream["url"]
    assert (there.location.line, there.location.column) == (6, 14)


LIBRARY = """\
spec_version: "0.1.0"
decisions:
  d:
    options: {a: {}, b: {}}
outputs:
  out:
    type: metric
    format: json
    decisions: [d]
    recipe:
      command: python make.py '{decisions.d}' '{output}'
"""
"""An analysis whose `out` is built per universe."""

OWN_UNIVERSE = """\
spec_version: "0.1.0"
analyses:
  lib: {path: lib}
decisions:
  e:
    options: {a: {}, b: {}}
outputs:
  result:
    type: metric
    format: json
    inputs: [lib.out]
    recipe:
      command: python make.py '{inputs.lib.out}' '{output}'
  other:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  uses_e:
    type: metric
    format: json
    decisions: [e]
    recipe:
      command: python make.py '{decisions.e}' '{output}'
universes:
  u1:
    decisions: {e: a}
"""
"""An analysis whose own `u1` reads `lib.out` through a `lib` it doesn't drive, and uses its key
`e` through `uses_e`, which nothing reads (Results *uses*)."""


def test_a_must_found_only_as_its_own_root_is_reported_at_its_place(tmp_path: Path) -> None:
    """Validated as its own root, `remote` builds its `u1`, where `result` reads `lib.out`
    though `lib` isn't built there; this root builds no universe of `remote`'s, so only that
    pass finds the two rules broken. Each is reported at its place in the commit's file, beside
    DECLARED_ANALYSIS_INVALID, which names them as related places."""
    files = {"astra.yaml": OWN_UNIVERSE, "lib/astra.yaml": LIBRARY}
    remote = repository(tmp_path / "remote", files)
    head = git(remote, "rev-parse", "HEAD").strip()
    text = declaring(
        f"{{remote: {{url: '{remote.as_uri()}', commit: '{head}'}}}}", "[remote.other]"
    )
    report = api.validate(repository(tmp_path / "root", {"astra.yaml": text}))
    place = ("astra.yaml", "/outputs/result/inputs/0", head)
    assert found(report) == {
        ("DECLARED_ANALYSIS_INVALID", "astra.yaml", "/analyses/remote", None),
        ("NOT_BUILT_IN_UNIVERSE", *place),
        ("UNDRIVEN_DECLARATION", *place),
    }
    (invalid,) = [d for d in report.diagnostics if d.code == "DECLARED_ANALYSIS_INVALID"]
    inside = [d.location for d in report.diagnostics if d.location.commit == head]
    assert sorted(invalid.related, key=str) == sorted(inside, key=str)


DRIVES_LIB = OWN_UNIVERSE.replace(
    "    inputs: [lib.out]\n", "    decisions: [e]\n    inputs: [lib.out]\n"
).replace("{e: a}", "{e: a, lib.d: a}")
"""An analysis whose own `u1` drives `lib`, so that its `result`, built per universe, reads
`lib.out` where `lib` is built: valid as its own root."""

DRIVING_REMOTE = """\
spec_version: "0.1.0"
analyses:
  remote: {{url: '{url}', commit: '{commit}'}}
outputs:
  result:
    type: metric
    format: json
    inputs: [remote.result]
    recipe:
      command: python make.py '{{inputs.remote.result}}' '{{output}}'
universes:
  u1:
    decisions: {{remote.e: a}}
"""
"""A root whose `u1` drives `remote` by its `e`, but not `remote`'s `lib`."""


def test_a_must_found_only_under_this_root_has_the_declaration_as_a_related_place(
    tmp_path: Path,
) -> None:
    """`remote` is valid as its own root, so it isn't DECLARED_ANALYSIS_INVALID;
    under this root, whose `u1` drives it but not its `lib`, its `result` reads `lib.out` where
    `lib` isn't built. That `MUST`, which only this root's pass finds in the commit's file, is
    reported there under its own code, with the declaration that leads to it as a related
    place."""
    files = {"astra.yaml": DRIVES_LIB, "lib/astra.yaml": LIBRARY}
    remote = repository(tmp_path / "remote", files)
    head = git(remote, "rev-parse", "HEAD").strip()
    assert api.validate(remote).diagnostics == ()
    text = DRIVING_REMOTE.format(url=remote.as_uri(), commit=head)
    report = api.validate(repository(tmp_path / "root", {"astra.yaml": text}))
    assert found(report) == {
        ("NOT_BUILT_IN_UNIVERSE", "astra.yaml", "/outputs/result/inputs/0", head)
    }
    (diagnostic,) = report.diagnostics
    assert [(at.file, at.pointer, at.commit) for at in diagnostic.related] == [
        ("astra.yaml", "/analyses/remote", None)
    ]


def test_a_file_whose_version_has_no_schema_isnt_judged_invalid(
    broken: api.ValidationReport, upstream: dict[str, str]
) -> None:
    """DECLARED_ANALYSIS_INVALID isn't checked on an analysis from a commit whose file breaks
    UNSUPPORTED_SPEC_VERSION, which is reported in that file."""
    commit = upstream["unsupported"]
    assert ("UNSUPPORTED_SPEC_VERSION", "astra.yaml", "/spec_version", commit) in found(broken)
    assert not any(item[2] == "/analyses/unsupported" for item in found(broken))


def test_a_url_whose_top_holds_no_analysis_breaks_missing_declared_analysis(
    broken: api.ValidationReport,
) -> None:
    """The folder a `url` names is the top of its repository, which holds an astra.yaml file.
    Its analysis is undetermined, so it isn't judged invalid."""
    assert ("MISSING_DECLARED_ANALYSIS", "astra.yaml", "/analyses/empty/url", None) in found(broken)
    assert not any(
        item[2] in ("/analyses/empty", "/outputs/result/inputs/2") for item in found(broken)
    )


def test_nothing_else_is_reported(broken: api.ValidationReport) -> None:
    assert len(broken.diagnostics) == len(found(broken)) == 12
    assert not broken.valid


def test_a_commit_of_a_remote_with_a_valid_analysis_keeps_every_rule(
    tmp_path: Path, upstream: dict[str, str]
) -> None:
    """`up` is the top of the remote's repository at the commit, whose input and output
    the root reads; `older` declares a `path` and an earlier `commit`, got from the remote its
    file was read from, an ancestor of the commit the declaration is in."""
    url = upstream["url"]
    analyses = (
        f"{{up: {{url: '{url}', commit: '{upstream['valid']}'}}, "
        f"older: {{url: '{url}', commit: '{upstream['older']}'}}}}"
    )
    text = declaring(analyses, "[up.result, up.input1, older.before.result]")
    report = api.validate(repository(tmp_path, {"astra.yaml": text}))
    assert (report.diagnostics, report.valid) == ((), True)


def test_a_commit_kept_from_an_earlier_fetch_counts_as_got(tmp_path: Path) -> None:
    """Once fetched, the commit is got, though the remote is gone, and offline; offline, nothing
    is fetched."""
    remote = repository(tmp_path / "remote", {"astra.yaml": MINIMAL})
    head = git(remote, "rev-parse", "HEAD").strip()
    text = declaring(f"{{up: {{url: '{remote.as_uri()}', commit: '{head}'}}}}", "[up.result]")
    root = repository(tmp_path / "root", {"astra.yaml": text})
    runner = CliRunner()
    first = runner.invoke(main, ["validate", str(root), "--offline"], prog_name="astra")
    assert first.exit_code == 1 and "REMOTE_UNREACHABLE" in first.stdout
    assert runner.invoke(main, ["validate", str(root)], prog_name="astra").exit_code == 0
    remote.rename(tmp_path / "gone")
    assert api.validate(root).diagnostics == ()
    assert runner.invoke(main, ["validate", str(root), "--offline"]).exit_code == 0


def test_a_commit_further_in_is_reported_on_the_outermost_declaration(tmp_path: Path) -> None:
    """The root declares `stage` by path, `stage` declares `upstream` by url, and `upstream`
    declares `nested` by url, whose commit can't be got: the error is on `stage`'s declaration
    of `upstream`. DECLARED_ANALYSIS_INVALID isn't checked on it, and only `nested` is
    undetermined: `upstream`'s MISSING_DECLARED_ANALYSIS and addresses into it are checked."""
    nested = f"nested: {{url: '{NOWHERE}', commit: '{ZERO}'}}, gone: {{path: nothere}}"
    remote = repository(
        tmp_path / "remote", {"astra.yaml": declaring(f"{{{nested}}}", "[nested.result]")}
    )
    head = git(remote, "rev-parse", "HEAD").strip()
    stage = declaring(
        f"{{upstream: {{url: '{remote.as_uri()}', commit: '{head}'}}}}",
        "[upstream.result, upstream.nothing]",
    )
    files = {"astra.yaml": declaring("{stage: {path: stage}}"), "stage/astra.yaml": stage}
    report = api.validate(repository(tmp_path / "root", files))
    assert found(report) == {
        ("REMOTE_UNREACHABLE", "stage/astra.yaml", "/analyses/upstream", None),
        ("UNRESOLVED_ADDRESS", "stage/astra.yaml", "/outputs/result/inputs/1", None),
        ("MISSING_DECLARED_ANALYSIS", "astra.yaml", "/analyses/gone/path", head),
    }


def test_the_cli_shows_a_commits_file_with_its_commit(
    upstream: dict[str, str], tmp_path: Path
) -> None:
    """Text grouped by file, a file read at a commit named with it, with `--json` as with
    text."""
    url, commit = upstream["url"], upstream["unresolved"]
    text = declaring(f"{{up: {{url: '{url}', commit: '{commit}'}}}}")
    root = repository(tmp_path, {"astra.yaml": text})
    result = CliRunner().invoke(main, ["validate", str(root)], prog_name="astra")
    assert result.exit_code == 1
    assert f"astra.yaml at {commit} from {url}\n" in result.stdout
    result = CliRunner().invoke(main, ["validate", str(root), "--json"], prog_name="astra")
    assert f"astra.yaml at {commit} from {url}\n" in json.loads(result.stdout)


# --- in the declaring repository: COMMIT_NOT_FOUND, COMMIT_NOT_ANCESTOR, and the rest at a commit


@pytest.fixture(scope="module")
def history(
    shared_cache: None, tmp_path_factory: pytest.TempPathFactory
) -> tuple[api.ValidationReport, dict[str, str]]:
    """A root declaring its own folder, and others, at commits of its own repository, each for
    a way of breaking a rule there."""
    top = tmp_path_factory.mktemp("history")
    data = repository(tmp_path_factory.mktemp("data"), {"x.csv": "1\n"})
    commits = {"base": commit(top, {"astra.yaml": MINIMAL})}
    git(top, "switch", "--quiet", "--create", "side")
    commits["side"] = commit(top, {"astra.yaml": MINIMAL + "label: side\n"})
    git(top, "switch", "--quiet", "-")
    commits["reserved"] = commit(
        top, {"astra.yaml": reading({"x": "results/x.csv"}), "results/x.csv": "1\n"}
    )
    git(top, "submodule", "--quiet", "add", str(data), "data")
    commits["submodule"] = commit(top, {"astra.yaml": reading({"x": "data/x.csv"})})
    commits["inner"] = commit(
        top, {"astra.yaml": declaring(f"{{gone: {{path: ., commit: '{ZERO}'}}}}")}
    )
    commits["late"] = commit(
        top, {"astra.yaml": declaring(f"{{side: {{path: ., commit: '{commits['side']}'}}}}")}
    )
    at = {name: f"{{path: ., commit: '{commits[name]}'}}" for name in commits}
    analyses = (
        f"{{zero: {{path: ., commit: '{ZERO}'}}, sha256: {{path: ., commit: '{'f' * 64}'}}, "
        f"side: {at['side']}, later: {{path: later, commit: '{commits['base']}'}}, "
        f"up: {{path: .., commit: '{commits['base']}'}}, reserved: {at['reserved']}, "
        f"submodule: {at['submodule']}, inner: {at['inner']}, late: {at['late']}}}"
    )
    (top / "later").mkdir()
    (top / "later" / "astra.yaml").write_text(MINIMAL)  # in the working tree, not at the commit
    (top / "astra.yaml").write_text(declaring(analyses, "[zero.result]"))
    return api.validate(top), commits


def test_a_commit_the_repository_hasnt_breaks_commit_not_found(
    history: tuple[api.ValidationReport, dict[str, str]],
) -> None:
    """A `path` with a `commit`, in a file not read from a remote, names a commit of the
    repository that holds the declaring file: in the working tree, and in a file read at a
    local commit. Neither MISSING_DECLARED_ANALYSIS, DECLARED_ANALYSIS_INVALID nor
    COMMIT_NOT_ANCESTOR is checked on it, nor any address through it."""
    report, commits = history
    assert {item for item in found(report) if item[0] == "COMMIT_NOT_FOUND"} == {
        ("COMMIT_NOT_FOUND", "astra.yaml", "/analyses/zero/commit", None),
        ("COMMIT_NOT_FOUND", "astra.yaml", "/analyses/sha256/commit", None),
        ("COMMIT_NOT_FOUND", "astra.yaml", "/analyses/gone/commit", commits["inner"]),
    }
    assert ("DECLARED_ANALYSIS_INVALID", "astra.yaml", "/analyses/inner", None) in found(report)
    assert not any(
        item[2] in ("/analyses/zero", "/outputs/result/inputs/0") for item in found(report)
    )
    (inside,) = [d for d in report.diagnostics if d.location.commit == commits["inner"]]
    assert inside.location.url is None  # a local commit came from no remote


def test_a_commit_off_the_history_breaks_commit_not_ancestor(
    history: tuple[api.ValidationReport, dict[str, str]],
) -> None:
    """COMMIT_NOT_ANCESTOR: the commit should be an ancestor of HEAD, for a
    declaration in the working tree, or of the commit the declaration is in. A SHOULD: a
    warning, and the analysis at `late` stays valid, so isn't judged invalid."""
    report, commits = history
    assert {d for d in report.diagnostics if d.code == "COMMIT_NOT_ANCESTOR"} == {
        d for d in report.diagnostics if d.level == "warning"
    }
    assert {item for item in found(report) if item[0] == "COMMIT_NOT_ANCESTOR"} == {
        ("COMMIT_NOT_ANCESTOR", "astra.yaml", "/analyses/side/commit", None),
        ("COMMIT_NOT_ANCESTOR", "astra.yaml", "/analyses/side/commit", commits["late"]),
    }
    assert not any(item[2] == "/analyses/late" for item in found(report))


def test_a_folder_read_at_its_commit(history: tuple[api.ValidationReport, dict[str, str]]) -> None:
    """The folder a declaration with a `commit` names is read at that commit, where
    `later` holds no astra.yaml (MISSING_DECLARED_ANALYSIS), and measured from the top of the
    repository that holds it (DECLARATION_OUTSIDE_REPOSITORY)."""
    report, _ = history
    assert found(report) >= {
        ("MISSING_DECLARED_ANALYSIS", "astra.yaml", "/analyses/later/path", None),
        ("DECLARATION_OUTSIDE_REPOSITORY", "astra.yaml", "/analyses/up/path", None),
    }
    assert not any(item[2] in ("/analyses/later", "/analyses/up") for item in found(report))


def test_reserved_path_and_input_not_tracked_at_a_commit(
    history: tuple[api.ValidationReport, dict[str, str]],
) -> None:
    """Read at a commit: an input in `results/` (RESERVED_PATH), and one in a plain data
    submodule, which is no file of that commit's tree, reached through no gitlink
    (INPUT_NOT_TRACKED), though a path that looks for a file goes on through the gitlink, so it
    is no MISSING_INPUT_FILE; each reported twice, once as DECLARED_ANALYSIS_INVALID."""
    report, commits = history
    assert found(report) >= {
        ("RESERVED_PATH", "astra.yaml", "/inputs/x/path", commits["reserved"]),
        ("DECLARED_ANALYSIS_INVALID", "astra.yaml", "/analyses/reserved", None),
        ("INPUT_NOT_TRACKED", "astra.yaml", "/inputs/x/path", commits["submodule"]),
        ("DECLARED_ANALYSIS_INVALID", "astra.yaml", "/analyses/submodule", None),
    }


def test_nothing_else_is_reported_at_the_commits(
    history: tuple[api.ValidationReport, dict[str, str]],
) -> None:
    report, _ = history
    assert len(report.diagnostics) == len(found(report)) == 12


def test_a_verdict_that_rests_on_the_local_repository_isnt_kept(tmp_path: Path) -> None:
    """COMMIT_NOT_FOUND, in a file read at a local commit, reads the repository that holds it,
    which can come to have the commit. `prev` is invalid while its `side` is missing, and valid
    once it is fetched, with the warning that `side` isn't in its history; the first verdict
    isn't kept for the second."""
    other = repository(tmp_path / "other", {"astra.yaml": MINIMAL})
    side = git(other, "rev-parse", "HEAD").strip()
    top = tmp_path / "top"
    first = commit(top, {"astra.yaml": declaring(f"{{side: {{path: ., commit: '{side}'}}}}")})
    commit(top, {"astra.yaml": declaring(f"{{prev: {{path: ., commit: '{first}'}}}}")})
    assert found(api.validate(top)) == {
        ("COMMIT_NOT_FOUND", "astra.yaml", "/analyses/side/commit", first),
        ("DECLARED_ANALYSIS_INVALID", "astra.yaml", "/analyses/prev", None),
    }
    git(top, "fetch", "--quiet", str(other), "HEAD")
    assert found(api.validate(top)) == {
        ("COMMIT_NOT_ANCESTOR", "astra.yaml", "/analyses/side/commit", first)
    }


def test_an_earlier_commit_of_the_history_keeps_every_rule(tmp_path: Path) -> None:
    """`previous` names the root's own folder at an earlier commit, and `stage` a folder there,
    both read at it: an input and a folder removed since are there, tracked in that commit's
    tree, and the commit is an ancestor of HEAD."""
    top = tmp_path / "repo"
    files = {
        "astra.yaml": reading({"old": "data/old.csv"}),
        "data/old.csv": "1\n",
        "stage/astra.yaml": MINIMAL,
    }
    first = commit(top, files)
    at = f"{{path: ., commit: '{first}'}}"
    text = declaring(
        f"{{previous: {at}, stage: {{path: stage, commit: '{first}'}}}}",
        "[previous.old, stage.result]",
    )
    commit(top, {"astra.yaml": text}, remove=("data/old.csv", "stage/astra.yaml"))
    report = api.validate(top)
    assert (report.diagnostics, report.valid) == ((), True)


def test_the_repository_that_holds_a_file_in_a_submodule_is_the_submodules(
    tmp_path: Path,
) -> None:
    """For a file in a submodule, COMMIT_NOT_FOUND and COMMIT_NOT_ANCESTOR read the submodule's
    own repository, where HEAD is the submodule's."""
    library = tmp_path / "library"
    first = commit(library, {"astra.yaml": MINIMAL})
    commit(library, {"astra.yaml": MINIMAL + "label: later\n"})
    top = repository(tmp_path / "root", {"astra.yaml": declaring("{lib: {path: lib}}")})
    git(top, "submodule", "--quiet", "add", str(library), "lib")
    own = commit(top, {})
    text = declaring(
        f"{{older: {{path: ., commit: '{first}'}}, root: {{path: ., commit: '{own}'}}}}"
    )
    (top / "lib" / "astra.yaml").write_text(text)
    assert found(api.validate(top)) == {
        ("COMMIT_NOT_FOUND", "lib/astra.yaml", "/analyses/root/commit", None)
    }


# --- gitlinks at a commit, and identity ---


@pytest.fixture(scope="module")
def linked(
    shared_cache: None, tmp_path_factory: pytest.TempPathFactory
) -> tuple[api.ValidationReport, Path]:
    """A root whose submodule `lib` holds an invalid analysis, declared at a commit through the
    gitlink and by its own URL; a commit whose `.gitmodules` gives a URL nothing answers, whose
    gitlink's commit the submodule's checkout holds; and a later one whose gitlink pins a
    commit the checkout hasn't."""
    library = tmp_path_factory.mktemp("library")
    pinned = commit(library, {"astra.yaml": UNRESOLVED})
    top = repository(tmp_path_factory.mktemp("root"), {"astra.yaml": MINIMAL})
    git(top, "submodule", "--quiet", "add", str(library), "lib")
    through = commit(top, {})
    git(top, "config", "--file", ".gitmodules", "submodule.lib.url", NOWHERE)
    moved = commit(top, {})
    later = commit(library, {"astra.yaml": MINIMAL})
    git(top, "update-index", "--cacheinfo", f"160000,{later},lib")
    git(top, "commit", "--quiet", "--message", "later")
    gone = git(top, "rev-parse", "HEAD").strip()
    analyses = (
        f"{{then: {{path: lib, commit: '{through}'}}, again: {{url: '{library.as_uri()}', "
        f"commit: '{pinned}'}}, moved: {{path: lib, commit: '{moved}'}}, "
        f"gone: {{path: lib, commit: '{gone}'}}}}"
    )
    (top / "astra.yaml").write_text(declaring(analyses, "[moved.result, gone.result]"))
    return api.validate(top), library


def test_a_path_through_a_gitlink_at_a_commit_is_read_in_the_submodule(
    linked: tuple[api.ValidationReport, Path],
) -> None:
    """A path to the top of a submodule, read at a commit, names the same analysis as a `url`
    declaration of the submodule's repository at the commit the gitlink pins: its rule broken
    is reported once, in the submodule's file at that commit, read in the submodule's checkout,
    which holds it, so got from no remote; and each declaration is judged invalid."""
    report, _ = linked
    inside = [d for d in report.diagnostics if d.location.commit is not None]
    assert [(d.code, d.location.file, d.location.url) for d in inside] == [
        ("UNRESOLVED_ADDRESS", "astra.yaml", None)
    ]
    invalid = {item[2] for item in found(report) if item[0] == "DECLARED_ANALYSIS_INVALID"}
    assert invalid == {"/analyses/then", "/analyses/again", "/analyses/moved"}


def test_a_gitlinks_commit_a_local_repository_holds_counts_as_got(
    linked: tuple[api.ValidationReport, Path],
) -> None:
    """A gitlink's commit that the submodule's checkout holds is got before any fetch, though
    the URL `.gitmodules` gives at `moved` answers nothing. One the checkout hasn't is got from
    that URL, so at `gone` it can't be got (REMOTE_UNREACHABLE); its analysis is undetermined,
    and the address through it isn't checked."""
    report, _ = linked
    assert ("DECLARED_ANALYSIS_INVALID", "astra.yaml", "/analyses/moved", None) in found(report)
    root = {item for item in found(report) if item[3] is None}
    assert {item for item in root if item[2].startswith(("/analyses/gone", "/outputs"))} == {
        ("REMOTE_UNREACHABLE", "astra.yaml", "/analyses/gone", None)
    }
    assert len(report.diagnostics) == 5


def test_a_relative_submodule_url_is_resolved_as_git_resolves_it(tmp_path: Path) -> None:
    """`../library` resolves against the remote a commit was got from, and, for a local commit
    with no remote, against its repository's folder, where the submodule isn't checked out to
    hold the commit."""
    commit(tmp_path / "library", {"astra.yaml": MINIMAL})
    remote = repository(tmp_path / "remote", {"astra.yaml": declaring("{lib: {path: lib}}")})
    git(remote, "submodule", "--quiet", "add", "../library", "lib")
    pinned = commit(remote, {})
    text = declaring(
        f"{{remote: {{url: '{remote.as_uri()}', commit: '{pinned}'}}}}", "[remote.lib.result]"
    )
    assert api.validate(repository(tmp_path / "root", {"astra.yaml": text})).diagnostics == ()
    text = declaring(f"{{local: {{path: lib, commit: '{pinned}'}}}}", "[local.result]")
    git(remote, "submodule", "--quiet", "deinit", "--force", "lib")
    (remote / "astra.yaml").write_text(text)
    assert api.validate(remote).diagnostics == ()
