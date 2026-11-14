"""The commands `validate`, `schema`, `guide` and `spec`, on what they
promise: output, `--json` shape and exit codes. The others are in `test_commands.py`."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import validate
from astra.cli import COMMANDS, main
from astra.diagnostics import Catalogue
from tests.conftest import MINIMAL, analysis, git_init


def astra(*args: str, env: dict[str, str] | None = None) -> Result:
    return CliRunner().invoke(main, list(args), env=env)


def test_help_names_every_command() -> None:
    result = astra("--help")
    assert result.exit_code == 0
    for name in COMMANDS:
        assert f"  {name} " in result.stdout
    assert set(COMMANDS) == {
        "check",
        "guide",
        "info",
        "init",
        "paper",
        "plan",
        "schema",
        "spec",
        "universe",
        "validate",
    }


# --- validate ---


def test_validate_exits_0_for_a_valid_analysis(tmp_path: Path) -> None:
    result = astra("validate", str(analysis(git_init(tmp_path))))
    assert result.exit_code == 0
    assert "astra.yaml: valid, 0 error(s), 0 warning(s)" in result.stdout
    assert validate.unchecked(Catalogue.load()) == ()  # every validator rule is checked
    assert "aren't checked" not in result.stdout


def test_validate_prints_line_col_level_code_message_by_file(tmp_path: Path) -> None:
    folder = analysis(git_init(tmp_path), MINIMAL.replace("type: metric", "type: plot"))
    result = astra("validate", str(folder))
    assert result.exit_code == 1
    lines = result.stdout.splitlines()
    assert lines[0] == "astra.yaml"
    assert lines[1].startswith('  4:11 error INVALID_VALUE `type` is "plot"')
    assert "astra.yaml: invalid, 1 error(s), 0 warning(s)" in result.stdout


def test_validate_respects_no_color(tmp_path: Path) -> None:
    folder = analysis(git_init(tmp_path), MINIMAL + "name: x\n")
    coloured = astra("validate", str(folder), env={"FORCE_COLOR": "1"})
    plain = astra("validate", str(folder), env={"FORCE_COLOR": "1", "NO_COLOR": "1"})
    assert "\x1b[1;31m" in coloured.stdout
    assert "31m" not in plain.stdout


def test_validate_json_is_the_report_of_the_file_given(tmp_path: Path, outside: Path) -> None:
    """`astra-validation-report/1`, with no ANSI escape, colour forced or not; the exit code
    still carries pass or fail."""
    result = astra("validate", str(analysis(outside)), "--json", env={"FORCE_COLOR": "1"})
    assert result.exit_code == 1
    assert "\x1b" not in result.stdout
    report = json.loads(result.stdout)
    assert (report["shape"], report["valid"]) == ("astra-validation-report/1", False)
    assert [d["code"] for d in report["diagnostics"]] == ["NOT_IN_REPOSITORY"]
    result = astra("validate", str(analysis(git_init(tmp_path / "repo")) / "astra.yaml"), "--json")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "shape": "astra-validation-report/1",
        "root": "astra.yaml",
        "valid": True,
        "diagnostics": [],
        "unchecked": [],
    }


def test_validate_takes_an_astra_yaml_or_its_folder(tmp_path: Path) -> None:
    folder = analysis(git_init(tmp_path))
    assert astra("validate", str(folder / "astra.yaml")).exit_code == 0
    (folder / "universe.yaml").write_text("decisions: {}\n")
    result = astra("validate", str(folder / "universe.yaml"))
    assert result.exit_code == 2 and "universes are in astra.yaml" in result.stderr


def test_validate_with_no_file_validates_every_root_analysis_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each astra.yaml under the current folder that no other declares, hidden, vendored and
    results folders skipped; one declared is validated with the analysis that declares it."""
    top = git_init(tmp_path)
    declaring = MINIMAL + "analyses:\n  part: {path: part}\n"
    analysis(top / "one", declaring)
    analysis(top / "one" / "part")
    analysis(top / "two", MINIMAL + "name: x\n")
    for skipped in (".hidden", "node_modules", "results"):
        analysis(top / skipped, MINIMAL + "name: x\n")
    monkeypatch.chdir(top)
    result = astra("validate")
    assert result.exit_code == 1
    assert "one/astra.yaml: valid" in result.stdout
    assert "two/astra.yaml: invalid" in result.stdout
    assert "part/astra.yaml:" not in result.stdout
    assert result.stdout.splitlines()[-1] == "1/2 file(s) failed validation: two/astra.yaml"
    monkeypatch.chdir(top / "one")
    result = astra("validate", "--json")
    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert (document["shape"], document["valid"]) == ("astra-validation-reports/1", True)
    assert [report["shape"] for report in document["reports"]] == ["astra-validation-report/1"]
    monkeypatch.chdir(top)
    document = json.loads(astra("validate", "--json").stdout)
    assert [(r["root"], r["valid"]) for r in document["reports"]] == [
        ("one/astra.yaml", True),
        ("two/astra.yaml", False),
    ]
    assert document["valid"] is False


def test_validate_with_no_file_and_no_analysis_here_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_init(tmp_path))
    result = astra("validate")
    assert (result.exit_code, result.stdout) == (1, "Error: No astra.yaml found here.\n")


def test_validate_reads_the_current_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(analysis(git_init(tmp_path)))
    result = astra("validate")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[-1] == "All 1 file(s) passed validation."


def test_validate_exits_2_where_there_is_no_analysis(tmp_path: Path) -> None:
    result = astra("validate", str(git_init(tmp_path)))
    assert result.exit_code == 2
    assert result.stderr.startswith("astra: ")
    assert "has no astra.yaml" in result.stderr
    assert astra("validate", str(tmp_path / "missing")).exit_code == 2
    (tmp_path / "file").write_text("x")
    assert astra("validate", str(tmp_path / "file")).exit_code == 2


def test_an_internal_error_exits_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from astra import api

    def broken(path: object, **options: object) -> None:
        raise RuntimeError("broken")

    monkeypatch.setattr(api, "validate", broken)
    result = astra("validate", str(tmp_path))
    assert result.exit_code == 2
    assert "internal error: RuntimeError: broken" in result.stderr


# --- guide, spec, schema ---


def test_guide_prints_astra_specs_llms_txt() -> None:
    result = astra("guide")
    assert result.exit_code == 0
    assert result.stdout_bytes == (files("astra") / "docs" / "llms.txt").read_bytes()


def test_spec_prints_the_concept_summary() -> None:
    result = astra("spec")
    assert result.exit_code == 0
    assert "ASTRA specification -- concept vocabulary" in result.stdout
    assert "astra spec <term> for detail" in result.stdout


def test_spec_describes_a_term_whatever_its_case() -> None:
    result = astra("spec", "evidence")
    assert result.exit_code == 0
    assert result.stdout.startswith("# Evidence\n")
    assert "doi" in result.stdout and "artifact" in result.stdout


def test_spec_of_an_unknown_term_lists_the_valid_ones_and_exits_1() -> None:
    result = astra("spec", "[nothing]")
    assert result.exit_code == 1
    assert result.stdout.startswith("Unknown term: [nothing]\nValid terms: Analysis, ")


def test_spec_full_dumps_every_entry() -> None:
    result = astra("spec", "--full")
    assert result.exit_code == 0
    for heading in ("# Analysis", "# Universe", "# Insight"):
        assert heading in result.stdout
    assert astra("spec", "--full", "output").exit_code == 2


@pytest.mark.parametrize(
    ("name", "file"), [("analysis", "analysis.yaml"), ("insights", "insight.yaml")]
)
def test_schema_show_prints_astra_specs_linkml_schema(name: str, file: str) -> None:
    result = astra("schema", "show", name)
    assert result.exit_code == 0
    assert result.stdout_bytes == (files("astra.schema") / file).read_bytes()


def test_schema_show_has_no_universe_schema() -> None:
    """Universes are part of the analysis schema since ASTRA 0.1."""
    assert astra("schema", "show", "universe").exit_code == 2


def test_schema_export_writes_each_linkml_schema(tmp_path: Path) -> None:
    result = astra("schema", "export", "-o", str(tmp_path / "schemas"))
    assert result.exit_code == 0
    written = {path.name for path in (tmp_path / "schemas").iterdir()}
    assert {"analysis.yaml", "insight.yaml"} <= written
