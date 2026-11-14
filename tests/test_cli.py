"""The commands `validate`, `schema`, `rules`, `guide`, `spec` and `completion`, on what they
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
    assert {"validate", "info", "universe", "init", "cache"} <= set(COMMANDS)


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


def test_validate_json_is_the_report_as_one_json_string(tmp_path: Path, outside: Path) -> None:
    """The text report, as one JSON-encoded string with no ANSI escape, colour forced or not,
    safe to embed in any JSON document; the exit code still carries pass or fail."""
    result = astra("validate", str(analysis(outside)), "--json", env={"FORCE_COLOR": "1"})
    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert isinstance(report, str) and "\x1b" not in report
    assert "error NOT_IN_REPOSITORY" in report and "invalid, 1 error(s)" in report
    result = astra("validate", str(analysis(git_init(tmp_path / "repo"))), "--json")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == "astra.yaml: valid, 0 error(s), 0 warning(s)\n"


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
    assert result.stdout.splitlines()[-1] == "1/2 analysis(es) failed validation: two/astra.yaml"
    monkeypatch.chdir(top / "one")
    result = astra("validate", "--json")
    assert result.exit_code == 0
    assert json.loads(result.stdout).endswith("All 1 analysis(es) passed validation.\n")


def test_validate_with_no_file_and_no_analysis_here_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_init(tmp_path))
    result = astra("validate")
    assert (result.exit_code, result.stdout) == (1, "Error: no astra.yaml found here.\n")


def test_validate_reads_the_current_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(analysis(git_init(tmp_path)))
    result = astra("validate")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[-1] == "All 1 analysis(es) passed validation."


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


# --- schema, rules, guide ---


SCHEMAS = files("astra.schema") / "jsonschema"
RULES = files("astra.schema") / "rules" / "rules.json"


@pytest.mark.parametrize("name", ["analysis", "provenance", "provenance.open"])
def test_schema_show_prints_astra_specs_schema(name: str) -> None:
    result = astra("schema", "show", name)
    assert result.exit_code == 0
    assert result.stdout_bytes == (SCHEMAS / f"{name}.schema.json").read_bytes()


def test_schema_export_writes_the_three(tmp_path: Path) -> None:
    result = astra("schema", "export", str(tmp_path / "out"))
    assert result.exit_code == 0
    for name in ("analysis", "provenance", "provenance.open"):
        written = (tmp_path / "out" / f"{name}.schema.json").read_bytes()
        assert written == (SCHEMAS / f"{name}.schema.json").read_bytes()
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        "analysis.schema.json",
        "provenance.open.schema.json",
        "provenance.schema.json",
    ]


def test_schema_show_refuses_another_name() -> None:
    assert astra("schema", "show", "record").exit_code == 2


def test_rules_lists_every_rule_by_layer() -> None:
    rules = json.loads(RULES.read_text("utf-8"))["rules"]
    result = astra("rules")
    assert result.exit_code == 0
    for rule in rules:
        assert f"  {rule['code']} {rule['level']} " in result.stdout
    assert result.stdout.index("validator") < result.stdout.index("NOT_IN_REPOSITORY")


def test_rules_lists_astra_tools_own_codes_as_its_own() -> None:
    """After rules.json's, astra-tools' own three, under a heading of their own."""
    last = json.loads(RULES.read_text("utf-8"))["rules"][-1]["code"]
    stdout = astra("rules").stdout
    own = stdout.index("validator, astra-tools' own")
    assert own > stdout.index(f"  {last} ")
    for code, level in (
        ("UNSUPPORTED_SPEC_VERSION", "MUST"),
        ("REMOTE_UNREACHABLE", "MUST"),
        ("COMMIT_NOT_ANCESTOR", "SHOULD"),
    ):
        assert stdout.index(f"  {code} {level} ") > own
    shown = astra("rules", "remote_unreachable")
    assert shown.stdout.splitlines()[:2] == ["REMOTE_UNREACHABLE", "validator, MUST, astra-tools"]


def test_rules_shows_one_rule_whatever_its_case() -> None:
    result = astra("rules", "absent_result")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[:2] == ["ABSENT_RESULT", "check, SHOULD"]
    assert "Status when broken: `absent`" in result.stdout
    assert astra("rules", "NO_SUCH_RULE").exit_code == 2


def test_guide_prints_astra_specs_llms_txt() -> None:
    result = astra("guide")
    assert result.exit_code == 0
    assert result.stdout_bytes == (files("astra") / "docs" / "llms.txt").read_bytes()


# --- spec ---


def test_spec_lists_the_classes_enums_and_types() -> None:
    result = astra("spec")
    assert result.exit_code == 0
    for line in ("Classes", "  Analysis ", "Enums", "  OutputType ", "Types", "  content_hash "):
        assert line in result.stdout


@pytest.mark.parametrize(
    "term, line",
    [
        ("Output.id", "  id (id, required) "),
        ("output", "Output (class)"),
        ("commit", "AnalysisDeclaration (class)"),
        ("spec_version", "Pattern: ^(0|[1-9][0-9]*)"),
    ],
)
def test_spec_describes_a_term(term: str, line: str) -> None:
    result = astra("spec", term)
    assert result.exit_code == 0
    assert line in result.stdout


def test_spec_refuses_an_unknown_term() -> None:
    result = astra("spec", "nothing_named_so")
    assert result.exit_code == 1
    assert result.stdout.splitlines()[0] == "Unknown term: nothing_named_so"
    assert result.stdout.splitlines()[1].startswith("Valid terms: ")
    assert "Insight" in result.stdout


def test_spec_full_shows_every_term_in_full() -> None:
    result = astra("spec", "--full")
    assert result.exit_code == 0
    assert "Insight (class)" in result.stdout and "Analysis (class)" in result.stdout
    assert "  claim (" in result.stdout  # a field, as a term in full shows it
    assert astra("spec", "Insight", "--full").exit_code == 2


# --- completion ---


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_prints_the_shells_script(shell: str) -> None:
    result = astra("completion", shell)
    assert result.exit_code == 0
    assert "_ASTRA_COMPLETE" in result.stdout


def test_completion_refuses_another_shell() -> None:
    assert astra("completion", "tcsh").exit_code == 2
