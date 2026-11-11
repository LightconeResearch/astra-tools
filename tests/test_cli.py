"""The six commands of phase 0, on what they promise: output, `--json` shape and exit codes
(design §4.12). Phase 1's are in `test_commands.py`."""

from __future__ import annotations

import json
import sys
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
    assert validate.unchecked(Catalogue.load()) == ()  # phase 1 checks every validator rule
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


def test_validate_json_is_the_report(tmp_path: Path, outside: Path) -> None:
    result = astra("validate", str(analysis(outside)), "--json")
    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert list(report) == ["shape", "root", "valid", "diagnostics", "unchecked"]
    assert report["shape"] == "astra-validation-report/1"
    assert [d["code"] for d in report["diagnostics"]] == ["NOT_IN_REPOSITORY"]
    result = astra("validate", str(analysis(git_init(tmp_path / "repo"))), "--json")
    assert (result.exit_code, json.loads(result.stdout)["valid"]) == (0, True)


def test_validate_reads_the_current_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(analysis(git_init(tmp_path)))
    assert astra("validate").exit_code == 0


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


SCHEMAS = files("astra.schema") / "generated"


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
    rules = json.loads((SCHEMAS / "rules.json").read_text("utf-8"))["rules"]
    result = astra("rules")
    assert result.exit_code == 0
    for rule in rules:
        assert f"  {rule['code']} {rule['level']} " in result.stdout
    assert result.stdout.index("validator") < result.stdout.index("NOT_IN_REPOSITORY")


def test_rules_lists_astra_tools_own_codes_as_its_own() -> None:
    """Design §3: after rules.json's, astra-tools' own three, under a heading of their own."""
    last = json.loads((SCHEMAS / "rules.json").read_text("utf-8"))["rules"][-1]["code"]
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
    assert astra("spec", "nothing_named_so").exit_code == 2


def test_spec_without_the_reference_extra_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "linkml_runtime", None)
    monkeypatch.setitem(sys.modules, "linkml_runtime.utils.schemaview", None)
    monkeypatch.setitem(sys.modules, "linkml_runtime.linkml_model.meta", None)
    result = astra("spec")
    assert result.exit_code == 2
    assert "[reference]" in result.stderr


# --- completion ---


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_prints_the_shells_script(shell: str) -> None:
    result = astra("completion", shell)
    assert result.exit_code == 0
    assert "_ASTRA_COMPLETE" in result.stdout


def test_completion_refuses_another_shell() -> None:
    assert astra("completion", "tcsh").exit_code == 2
