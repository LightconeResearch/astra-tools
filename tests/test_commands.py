"""The commands `info` and `init`, and the `astra.api` functions
they call, on what they promise: output, exit codes and what they leave on disk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.cli import main
from tests.conftest import MINIMAL, analysis, git, git_init, repository


def astra(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


# --- api.bind ---


def test_bind_gives_the_stack_and_its_files_diagnostics(tmp_path: Path) -> None:
    """Every analysis of the stack, the root first, with the schema diagnostics of a declared
    file that isn't a valid document; none where the root's file isn't one."""
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


def test_info_shows_the_analysis_in_brief(tmp_path: Path) -> None:
    """The root's label and counts, then its inputs, outputs, decisions (those of the analyses
    it declares after its own) and universes; a switch with the decision it switches on and its
    cases (Elements *switch*). It checks nothing, so a declaration that reaches nothing is
    counted, not reported."""
    files = {"astra.yaml": MINIMAL, "subanalysis/astra.yaml": SUBANALYSIS, "data/input1.csv": "1\n"}
    top = repository(tmp_path, files)
    switch = "  switch1:\n    switch: decision1\n    cases: {a: output1, b: input1}\nuniverses:\n"
    repository(top, {"astra.yaml": ROOT.replace("universes:\n", switch, 1)})
    result = astra("info", "-f", str(top / "astra.yaml"))
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[:2] == ["Example analysis", "Spec version: 0.1.0"]
    assert "Inputs: 1 | Outputs: 2 | Decisions: 1 | Universes: 2" in lines
    assert "Layout: 2 sub-analyses in ./nothere/, ./subanalysis/" in lines
    shown = " ".join(result.stdout.split())
    for part in ("Inputs:", "Outputs:", "Decisions:", "Universes:"):
        assert f"\n{part}\n" in result.stdout
    assert "input1 │ data/input1.csv" in shown
    assert "switch1 │ switch │ on decision1 (a: output1, b: input1)" in shown
    assert "decision1:" in shown and "Analysis: subanalysis" in shown
    assert "u2: derived from u1" in shown


def test_info_with_no_stack_to_show_exits_1(tmp_path: Path, outside: Path) -> None:
    """A root whose file isn't a valid document, or in no repository, has no stack."""
    for folder in (analysis(git_init(tmp_path / "repo"), MINIMAL + "name: x\n"), analysis(outside)):
        result = astra("info", "--file", str(folder / "astra.yaml"))
        assert result.exit_code == 1
        assert "astra validate" in result.stderr


def test_info_exits_1_where_there_is_no_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_init(tmp_path))
    result = astra("info")
    assert result.exit_code == 1
    assert result.stderr.startswith("Error: No astra.yaml found in current directory or parents.")


def test_info_reads_the_astra_yaml_here_or_above(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    top = repository(tmp_path, {"astra.yaml": MINIMAL})
    (top / "src").mkdir()
    monkeypatch.chdir(top / "src")
    result = astra("info")
    assert result.exit_code == 0
    assert "Inputs: 0 | Outputs: 1 | Decisions: 0 | Universes: 0" in result.stdout


def test_info_shows_only_the_parts_asked_for(tmp_path: Path) -> None:
    files = {"astra.yaml": MINIMAL, "subanalysis/astra.yaml": SUBANALYSIS, "data/input1.csv": "1\n"}
    top = repository(tmp_path, files)
    repository(top, {"astra.yaml": ROOT})
    shown = astra("info", "-f", str(top / "astra.yaml"), "-d", "-i").stdout
    parts = [part for part in ("Inputs:", "Outputs:", "Decisions:", "Universes:")]
    assert [part for part in parts if f"\n{part}\n" in shown] == ["Inputs:", "Decisions:"]


def test_info_json_is_every_analysis_of_the_stack(tmp_path: Path) -> None:
    files = {"astra.yaml": MINIMAL, "subanalysis/astra.yaml": SUBANALYSIS, "data/input1.csv": "1\n"}
    top = repository(tmp_path, files)
    repository(top, {"astra.yaml": ROOT})
    result = astra("info", "-f", str(top / "astra.yaml"), "--json")
    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document["shape"] == "astra-info/1"
    root, sub = document["analyses"][:2]
    assert (root["file"], root["label"]) == ("astra.yaml", "Example analysis")
    assert root["analyses"] == {"subanalysis": "subanalysis/astra.yaml", "missing": None}
    assert root["inputs"] == {"input1": {"path": "data/input1.csv", "description": None}}
    assert root["outputs"]["output1"]["type"] == "metric"
    assert list(root["decisions"]["decision1"]["options"]) == ["a", "b"]
    assert root["universes"]["u2"]["derived_from"] == "u1"
    assert sub["file"] == "subanalysis/astra.yaml"


# --- init ---


def test_init_makes_an_analysis_in_a_new_repository_that_validates(tmp_path: Path) -> None:
    folder = tmp_path / "new" / "analysis"
    result = astra("init", str(folder))
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "✓ created astra.yaml",
        "✓ created .gitignore",
        "✓ created .git",
        f"✓ Converged ASTRA analysis scaffold: {folder}",
    ]
    assert (folder / ".git").is_dir() and (folder / ".gitignore").is_file()
    assert api.validate(folder).diagnostics == ()
    assert astra("validate", str(folder)).exit_code == 0


def test_init_converges_and_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run again, it changes nothing; on a folder with an astra.yaml of its own, it keeps it.
    Where git knows who commits, the new repository gets a first commit."""
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "astra-tools tests")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "tests@astra.invalid")
    folder = tmp_path / "analysis"
    assert astra("init", str(folder)).exit_code == 0
    assert git(folder, "log", "--format=%s").strip() == "Initial ASTRA analysis structure"
    again = astra("init", str(folder))
    assert (again.exit_code, again.stdout) == (0, f"✓ {folder} already converged\n")
    (folder / "astra.yaml").write_text("mine\n")
    assert astra("init", str(folder)).exit_code == 0
    assert (folder / "astra.yaml").read_text() == "mine\n"
    assert astra("init", str(folder), "--no-git").exit_code == 2  # an analysis is in a repository


def test_init_check_writes_nothing_and_json_reports(tmp_path: Path) -> None:
    folder = tmp_path / "analysis"
    result = astra("init", str(folder), "--check", "--json")
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "converged": False,
        "created": ["astra.yaml", ".gitignore", ".git"],
        "repaired": [],
        "unchanged": [],
        "warnings": [],
    }
    assert not folder.exists()
    assert astra("init", str(folder)).exit_code == 0
    done = astra("init", str(folder), "--check")
    assert (done.exit_code, done.stdout) == (0, f"✓ {folder} is converged — nothing to do\n")


def test_create_boilerplate_writes_an_empty_analysis_and_nothing_else(tmp_path: Path) -> None:
    """What `astra init` and downstream tools scaffold through: an astra.yaml, valid once its
    folder is in a repository, with no universes folder."""
    from astra.scaffold import create_boilerplate

    top = git_init(tmp_path)
    create_boilerplate(top / "stage")
    assert [path.name for path in (top / "stage").iterdir()] == ["astra.yaml"]
    assert 'label: "stage"' in (top / "stage" / "astra.yaml").read_text()
    assert api.validate(top / "stage").diagnostics == ()


def test_init_inside_a_working_tree_makes_no_repository_through_the_cli(tmp_path: Path) -> None:
    top = git_init(tmp_path)
    result = astra("init", str(top / "stage"))
    assert result.exit_code == 0 and "✓ created .git" not in result.stdout.splitlines()
    assert not (top / "stage" / ".git").exists()


def test_init_exits_2_for_a_file(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("x")
    assert astra("init", str(tmp_path / "file")).exit_code == 2


def test_init_makes_the_repository_where_git_knows_no_one_to_commit_as(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a user name and email, there is no first commit, and the repository is made
    all the same."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("EMAIL", "")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.delenv(f"GIT_{who}_NAME", raising=False)
        monkeypatch.delenv(f"GIT_{who}_EMAIL", raising=False)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "user.useConfigOnly")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    folder = tmp_path / "analysis"
    result = astra("init", str(folder))
    assert result.exit_code == 0 and "✓ created .git" in result.stdout
    assert (folder / ".git").is_dir() and (folder / "astra.yaml").is_file()
    assert astra("init", str(folder), "--check").exit_code == 0
