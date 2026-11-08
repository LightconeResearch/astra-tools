"""The commands of phase 1, `info`, `universe`, `init` and `cache`, and the `astra.api` functions
they call, on what they promise: output, exit codes and what they leave on disk (design §4.12).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api, cache
from astra.cli import main
from tests.conftest import MINIMAL, analysis, git, git_init, repository


def astra(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


# --- api.bind ---


def test_bind_gives_the_stack_and_its_files_diagnostics(tmp_path: Path) -> None:
    """Every analysis of the stack, the root first, with the schema diagnostics of a declared
    file that isn't a valid document (design §4.4); none where the root's file isn't one."""
    root = MINIMAL + "analyses: {sub: {path: sub}}\n"
    top = repository(tmp_path, {"astra.yaml": root, "sub/astra.yaml": MINIMAL + "name: x\n"})
    bound = api.bind(top)
    assert bound.stack is not None
    assert [str(identity) for identity in bound.stack.analyses] == [".", "sub"]
    assert [(d.code, d.location.file) for d in bound.diagnostics] == [
        ("UNKNOWN_FIELD", "sub/astra.yaml")
    ]
    (top / "astra.yaml").write_text(MINIMAL + "name: x\n")
    assert api.bind(top).stack is None


# --- info ---


ROOT = """\
spec_version: "0.1.0"
label: Example analysis
analyses:
  subanalysis: {path: subanalysis}
  missing: {path: nothere}
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    inputs: [input1]
    decisions: [decision1]
    recipe:
      command: python src/output1.py '{inputs.input1}' '{decisions.decision1}' '{output}'
universes:
  u1:
    decisions: {decision1: a, subanalysis.decision1: a}
  u2:
    derived_from: u1
    decisions: {decision1: b}
"""

SUBANALYSIS = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    decisions: [decision1]
    recipe:
      command: python make.py '{decisions.decision1}' '{output}'
"""


def test_info_shows_each_analysis_of_the_stack_in_brief(tmp_path: Path) -> None:
    """The root first, then each analysis it declares, by path and at a commit (§15, §17), each
    with its declarations, inputs, outputs, decisions and universes. It checks nothing, so a
    declaration that reaches nothing is shown, not reported."""
    files = {"astra.yaml": MINIMAL, "subanalysis/astra.yaml": SUBANALYSIS, "data/input1.csv": "1\n"}
    top = repository(tmp_path, files)
    first = git(top, "rev-parse", "HEAD").strip()
    declared = f"  previous: {{path: ., commit: '{first}'}}\ninputs:\n"
    repository(top, {"astra.yaml": ROOT.replace("inputs:\n", declared, 1)})
    result = astra("info", str(top))
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[:10] == [
        "astra.yaml  Example analysis",
        "  analyses  subanalysis: subanalysis/astra.yaml",
        "            missing: nothing (missing)",
        f"            previous: astra.yaml at {first}",
        "  inputs    input1: data/input1.csv",
        "  outputs   output1: metric, json",
        "  decisions decision1: a, b",
        "  universes u1",
        "            u2: derived from u1",
        "subanalysis/astra.yaml",
    ]
    assert f"astra.yaml at {first}" in lines[10:]
    assert "  outputs   result: metric, json" in lines


def test_info_with_no_stack_to_show_exits_1(tmp_path: Path, outside: Path) -> None:
    """A root whose file isn't a valid document, or in no repository, has no stack."""
    for folder in (analysis(git_init(tmp_path / "repo"), MINIMAL + "name: x\n"), analysis(outside)):
        result = astra("info", str(folder))
        assert result.exit_code == 1
        assert "astra validate" in result.stderr


def test_info_exits_2_where_there_is_no_analysis(tmp_path: Path) -> None:
    result = astra("info", str(git_init(tmp_path)))
    assert result.exit_code == 2
    assert "has no astra.yaml" in result.stderr


# --- universe ---


UNIVERSES = """\
spec_version: "0.1.0"
analyses:
  subanalysis: {path: subanalysis}
decisions:
  decision1:
    options: {a: {}, b: {}}
  decision2:
    options: {a: {}, b: {}}
  decision3:
    when: [decision1.b]
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    decisions: [decision1, decision2]
    recipe:
      command: python make.py '{decisions.decision1}' '{decisions.decision2}' '{output}'
universes:
  u1:
    decisions: {decision1: a, decision2: a, subanalysis.decision1: a}
  u2:
    derived_from: u1
    decisions: {decision1: b, decision2: b, decision3: a}
  u3:
    derived_from: u2
    decisions: {decision1: a}   # the inherited decision3 is dropped
  u4:
    label: Derived from nothing
    derived_from: u9
  subanalysis_v1:
    analysis: subanalysis
    universe: v1
"""
"""§12's three universes and its import, and one with no effective selection (design §4.13
case 7)."""


@pytest.fixture(scope="module")
def universes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    sub = SUBANALYSIS + "universes:\n  v1:\n    decisions: {decision1: b}\n"
    files = {"astra.yaml": UNIVERSES, "subanalysis/astra.yaml": sub}
    return repository(tmp_path_factory.mktemp("universes"), files)


def test_universe_list_shows_the_universes_and_imports(universes: Path) -> None:
    result = astra("universe", "list", str(universes))
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "u1",
        "u2  derived from u1",
        "u3  derived from u2",
        "u4  derived from u9  Derived from nothing",
        "subanalysis_v1  imports subanalysis.v1",
    ]


@pytest.mark.parametrize(
    "universe, selects",
    [
        ("u1", ["decision1: a", "decision2: a", "subanalysis.decision1: a"]),
        (
            "u2",
            [
                "subanalysis.decision1: a  (from u1)",
                "decision1: b",
                "decision2: b",
                "decision3: a",
            ],
        ),
        (
            "u3",
            ["subanalysis.decision1: a  (from u1)", "decision2: b  (from u2)", "decision1: a"],
        ),
    ],
)
def test_universe_show_gives_the_effective_selection(
    universes: Path, universe: str, selects: list[str]
) -> None:
    """§12's table: what each universe selects once `derived_from` is resolved, each inherited
    selection with the universe it comes from; `u3` drops the `decision3` it inherits."""
    result = astra("universe", "show", universe, str(universes))
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0].split("  ")[0] == universe
    assert [line.strip() for line in lines[1:]] == selects


def test_universe_show_of_a_universe_with_no_effective_selection_exits_1(universes: Path) -> None:
    """design §4.13 case 7, and design §4.12."""
    result = astra("universe", "show", "u4", str(universes))
    assert result.exit_code == 1
    assert "no effective selection" in result.stderr


@pytest.mark.parametrize("universe", ["subanalysis_v1", "u9"])
def test_universe_show_of_an_import_or_of_nothing_is_a_usage_error(
    universes: Path, universe: str
) -> None:
    """An import selects nothing and isn't one of the analysis's universes (§12)."""
    result = astra("universe", "show", universe, str(universes))
    assert result.exit_code == 2
    assert "u1, u2, u3, u4" in result.stderr


# --- init ---


def test_init_makes_an_analysis_in_a_new_repository_that_validates(tmp_path: Path) -> None:
    folder = tmp_path / "new" / "analysis"
    result = astra("init", str(folder))
    assert result.exit_code == 0
    assert (folder / ".git").is_dir()
    assert "in a new git repository" in result.stdout
    assert api.validate(folder).diagnostics == ()
    assert astra("validate", str(folder)).exit_code == 0


def test_init_inside_a_working_tree_makes_no_repository(tmp_path: Path) -> None:
    """The analysis is in the repository that holds its folder."""
    top = git_init(tmp_path)
    assert api.init(top / "stage") == (top / "stage" / "astra.yaml", False)
    assert not (top / "stage" / ".git").exists()
    assert api.validate(top / "stage").diagnostics == ()


def test_init_exits_2_where_there_is_an_analysis_or_a_file(tmp_path: Path) -> None:
    folder = analysis(tmp_path / "analysis")
    result = astra("init", str(folder))
    assert result.exit_code == 2
    assert "has an astra.yaml already" in result.stderr
    assert (folder / "astra.yaml").read_text() == MINIMAL
    (tmp_path / "file").write_text("x")
    assert astra("init", str(tmp_path / "file")).exit_code == 2


# --- cache ---


def test_cache_path_prints_the_cache_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    result = astra("cache", "path")
    assert (result.exit_code, result.stdout) == (0, f"{cache.root()}\n")
    monkeypatch.setenv("ASTRA_CACHE_DIR", "relative")
    result = astra("cache", "path")
    assert result.exit_code == 2
    assert "ASTRA_CACHE_DIR" in result.stderr


def test_cache_clear_deletes_only_what_astra_keeps(tmp_path: Path) -> None:
    """The remote stores and the validity of analyses from a commit, and nothing else in
    the folder."""
    cache.put("validity", "key", b"value")
    (cache.root() / "remotes" / "store").mkdir(parents=True)
    (cache.root() / "mine.txt").write_text("not astra's")
    result = astra("cache", "clear")
    assert result.exit_code == 0
    assert sorted(path.name for path in cache.root().iterdir()) == ["mine.txt"]
    assert cache.get("validity", "key") is None
    assert astra("cache", "clear").exit_code == 0
