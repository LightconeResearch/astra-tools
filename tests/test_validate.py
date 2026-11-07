"""`validate`: the root `astra.yaml` by the parse and schema rules, UNSUPPORTED_SPEC_VERSION and
NOT_IN_REPOSITORY (§5, Annex A, Annex D cases 1, 2 and 11, Annex E), and the report it gives."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from astra import api
from astra.diagnostics import Catalogue
from tests.conftest import MINIMAL, SPEC, analysis, git_init


def pairs(report: api.ValidationReport) -> list[tuple[str, str]]:
    return [(d.code, d.location.pointer) for d in report.diagnostics]


def checked_in_repository(tmp_path: Path, text: str) -> api.ValidationReport:
    return api.validate(analysis(git_init(tmp_path / "repo"), text))


# --- §5: NOT_IN_REPOSITORY, and Annex D cases 2 and 11 ---


def test_an_analysis_outside_a_repository_breaks_not_in_repository(outside: Path) -> None:
    report = api.validate(analysis(outside))
    assert pairs(report) == [("NOT_IN_REPOSITORY", "")]
    assert report.diagnostics[0].level == "error"
    assert report.diagnostics[0].location.file == "astra.yaml"
    assert not report.valid


def test_an_analysis_in_a_working_tree_keeps_it(tmp_path: Path) -> None:
    """In the working tree, tracked or not: nothing needs committing (§5)."""
    report = api.validate(analysis(git_init(tmp_path)))
    assert (report.diagnostics, report.valid) == ((), True)


def test_an_analysis_in_a_subfolder_is_named_from_the_repository_top(tmp_path: Path) -> None:
    report = api.validate(analysis(git_init(tmp_path) / "stage" / "one"))
    assert (report.root, report.diagnostics) == ("stage/one/astra.yaml", ())


def test_outside_a_repository_the_parse_and_schema_rules_are_checked(outside: Path) -> None:
    """Annex D case 11: only the root's own file is checked, by the parse and schema rules; and
    by case 2, a file that breaks one isn't checked by NOT_IN_REPOSITORY (O6)."""
    report = api.validate(analysis(outside, MINIMAL + "name: Old\n"))
    assert pairs(report) == [("UNKNOWN_FIELD", "")]
    report = api.validate(analysis(outside, MINIMAL + "outputs: {}\n"))
    assert pairs(report) == [("DUPLICATE_KEY", "")]


# --- §5 Versions: UNSUPPORTED_SPEC_VERSION, and Annex D case 1 ---


@pytest.mark.parametrize("version", ["0.2.0", "1.0.0", "0.0.1", "0.10.0"])
def test_a_version_of_another_minor_breaks_unsupported_spec_version(
    tmp_path: Path, version: str
) -> None:
    """Its schema isn't run, so the unknown field isn't reported (Annex D case 1)."""
    text = MINIMAL.replace("0.1.0", version) + "name: x\n"
    report = checked_in_repository(tmp_path, text)
    assert pairs(report) == [("UNSUPPORTED_SPEC_VERSION", "/spec_version")]
    location = report.diagnostics[0].location
    assert (location.line, location.column) == (1, 15)


@pytest.mark.parametrize("version", ["0.1.0", "0.1.7", "0.1.12"])
def test_every_patch_of_0_1_keeps_it(tmp_path: Path, version: str) -> None:
    assert checked_in_repository(tmp_path, MINIMAL.replace("0.1.0", version)).valid


@pytest.mark.parametrize("version", ['"0.1"', '"0.2.0rc1"', '"00.1.0"', '"v0.1.0"'])
def test_a_malformed_version_is_read_by_the_0_1_schema(tmp_path: Path, version: str) -> None:
    """Annex D case 1: not UNSUPPORTED_SPEC_VERSION, but the schema's INVALID_VALUE."""
    report = checked_in_repository(tmp_path, MINIMAL.replace('"0.1.0"', version))
    assert pairs(report) == [("INVALID_VALUE", "/spec_version")]


def test_a_missing_version_is_read_by_the_0_1_schema(tmp_path: Path) -> None:
    """A file written before 0.1 has `version` and `name`: every schema error is reported."""
    text = MINIMAL.replace('spec_version: "0.1.0"', 'version: "0.0.11"\nname: Old')
    report = checked_in_repository(tmp_path, text)
    assert sorted(pairs(report)) == [
        ("MISSING_FIELD", ""),
        ("UNKNOWN_FIELD", ""),
        ("UNKNOWN_FIELD", ""),
    ]


def test_an_unsupported_version_outside_a_repository_is_reported_alone(outside: Path) -> None:
    """O8: the file breaks UNSUPPORTED_SPEC_VERSION, so NOT_IN_REPOSITORY isn't checked."""
    report = api.validate(analysis(outside, MINIMAL.replace("0.1.0", "0.2.0")))
    assert pairs(report) == [("UNSUPPORTED_SPEC_VERSION", "/spec_version")]


# --- Annex A: reading an astra.yaml ---


def test_a_version_written_as_a_number_is_a_number(tmp_path: Path) -> None:
    report = checked_in_repository(tmp_path, MINIMAL.replace('"0.1.0"', "0.1"))
    assert pairs(report) == [("WRONG_TYPE", "/spec_version")]


@pytest.mark.parametrize("text", ["", "# only a comment\n"])
def test_a_file_with_no_document_is_null(tmp_path: Path, text: str) -> None:
    assert pairs(checked_in_repository(tmp_path, text)) == [("WRONG_TYPE", "")]


def test_a_quoted_key_is_the_same_key(tmp_path: Path) -> None:
    """`a`, `'a'` and `"a"` are one key: DUPLICATE_KEY, at the second."""
    text = MINIMAL + "'outputs': {}\n"
    report = checked_in_repository(tmp_path, text)
    assert pairs(report) == [("DUPLICATE_KEY", "")]
    assert (report.diagnostics[0].location.line, report.diagnostics[0].location.column) == (8, 1)


@pytest.mark.parametrize("number", [".inf", "-.Inf", ".nan"])
def test_a_number_that_isnt_finite_breaks_invalid_syntax(tmp_path: Path, number: str) -> None:
    resources = f"      resources: {{cpus: {number}}}\n      command"
    report = checked_in_repository(tmp_path, MINIMAL.replace("      command", resources))
    assert pairs(report) == [("INVALID_SYNTAX", "")]
    assert report.diagnostics[0].location.line == 7


@pytest.mark.parametrize("key", ["1", "true", "null", "[a]"])
def test_a_key_that_isnt_a_string_breaks_invalid_syntax(tmp_path: Path, key: str) -> None:
    report = checked_in_repository(tmp_path, MINIMAL + f"tags: [x]\n{key}: x\n")
    assert pairs(report) == [("INVALID_SYNTAX", "")]


@pytest.mark.parametrize(
    "tag", ["!!timestamp 2026-10-26", "!!binary aGk=", "!local x", "!!int 1.5"]
)
def test_a_tag_outside_the_core_schema_breaks_invalid_syntax(tmp_path: Path, tag: str) -> None:
    """Annex A: read under the core schema, with no tag but its own; and `!!int` doesn't read
    `1.5`."""
    report = checked_in_repository(tmp_path, MINIMAL + f"label: {tag}\n")
    assert pairs(report) == [("INVALID_SYNTAX", "")]


def test_plain_scalars_are_typed_by_the_core_schema(tmp_path: Path) -> None:
    """A date, `yes`, `1_000` and `0b1` are strings, `0o17` a number, and `2.0` an integer
    (Annex A, YAML 1.2.2 §10.3.2)."""
    text = MINIMAL.replace(
        "      command", "      resources: {gpus: 2.0, cpus: 0o17}\n      command"
    )
    text += "label: 2026-10-26\ndescription: yes\ntags: [no, on, 1_000, 0b1]\n"
    assert checked_in_repository(tmp_path, text).diagnostics == ()


def test_a_pin_needs_no_quotes_and_a_url_needs_none_in_a_flow_map(tmp_path: Path) -> None:
    """`#` inside a token is literal (Annex A), and `{url: https://…}` is read whole
    (design §4.1, `pure=True`)."""
    text = f"""\
spec_version: "0.1.0"
analyses: {{up: {{url: https://example.org/up.git, commit: "{"0" * 40}"}}}}
outputs:
  result:
    type: metric
    format: json
    inputs: [up.output1#u1]  # a comment
    recipe:
      command: python make.py '{{inputs.up.output1#u1}}' '{{output}}'
"""
    assert checked_in_repository(tmp_path, text).diagnostics == ()


def test_a_pattern_ends_where_the_value_ends(tmp_path: Path) -> None:
    """A block scalar ends in a line break, which a pattern's `$` doesn't match before
    (ECMA-262, design §4.1): `format: |` gives "json\\n", which breaks INVALID_VALUE."""
    text = MINIMAL.replace("format: json", "format: |\n      json")
    report = checked_in_repository(tmp_path, text)
    assert pairs(report) == [("INVALID_VALUE", "/outputs/result/format")]


# --- Annex E: where a schema error is reported ---


def test_an_error_on_a_key_is_at_its_map_naming_the_key(tmp_path: Path) -> None:
    report = checked_in_repository(tmp_path, MINIMAL.replace("  result:", "  Result:"))
    (diagnostic,) = report.diagnostics
    assert (diagnostic.code, diagnostic.location.pointer) == ("INVALID_ID", "/outputs")
    assert diagnostic.location.key == "Result"
    assert (diagnostic.location.line, diagnostic.location.column) == (3, 3)


def test_an_unknown_field_is_at_its_object_naming_the_field(tmp_path: Path) -> None:
    text = MINIMAL.replace("    type: metric", "    from: x\n    type: metric") + "id: x\n"
    report = checked_in_repository(tmp_path, text)
    found = [
        (d.code, d.location.pointer, d.location.key, d.location.line) for d in report.diagnostics
    ]
    assert found == [
        ("UNKNOWN_FIELD", "/outputs/result", "from", 4),
        ("UNKNOWN_FIELD", "", "id", 9),
    ]


def test_a_map_that_lacks_two_fields_is_one_missing_field(tmp_path: Path) -> None:
    """jsonschema gives an error per missing field; the map gets one diagnostic naming both."""
    text = MINIMAL.split("    format:")[0]
    report = checked_in_repository(tmp_path, text)
    assert pairs(report) == [("MISSING_FIELD", "/outputs/result")]
    assert "`format`, `recipe`" in report.diagnostics[0].message


def test_a_value_is_placed_at_its_line_and_column(tmp_path: Path) -> None:
    report = checked_in_repository(tmp_path, MINIMAL.replace("type: metric", "type: plot"))
    (diagnostic,) = report.diagnostics
    assert (diagnostic.code, diagnostic.location.pointer) == (
        "INVALID_VALUE",
        "/outputs/result/type",
    )
    assert (diagnostic.location.line, diagnostic.location.column) == (4, 11)


# --- The report (design §4.11) ---


def test_unchecked_lists_the_validator_codes_this_build_doesnt_check(tmp_path: Path) -> None:
    """Every validator code of rules.json but the two phase 0 checks."""
    catalogue = Catalogue.load()
    expected = [
        code
        for code in catalogue.codes("validator")
        if code not in ("NOT_IN_REPOSITORY", "UNSUPPORTED_SPEC_VERSION")
    ]
    report = api.validate(analysis(git_init(tmp_path)))
    assert list(report.unchecked) == expected
    assert len(report.unchecked) == 32


def test_the_report_as_json(outside: Path) -> None:
    document = json.loads(json.dumps(api.validate(analysis(outside)).to_json()))
    assert document == {
        "shape": "astra-validation-report/1",
        "root": "astra.yaml",
        "valid": False,
        "diagnostics": [
            {
                "code": "NOT_IN_REPOSITORY",
                "level": "error",
                "message": document["diagnostics"][0]["message"],
                "location": {
                    "file": "astra.yaml",
                    "pointer": "",
                    "line": None,
                    "column": None,
                    "key": None,
                    "commit": None,
                    "url": None,
                },
                "related": [],
            }
        ],
        "unchecked": document["unchecked"],
    }
    assert len(document["unchecked"]) == 32


def test_a_folder_without_an_astra_yaml_is_no_analysis(tmp_path: Path) -> None:
    with pytest.raises(api.NoAnalysisError, match="no astra.yaml"):
        api.validate(git_init(tmp_path))
    (tmp_path / "astra.yaml").mkdir()
    with pytest.raises(api.NoAnalysisError, match="no astra.yaml"):
        api.validate(tmp_path)
    with pytest.raises(api.NoAnalysisError, match="isn't a folder"):
        api.validate(tmp_path / "missing")


def test_a_symlinked_astra_yaml_is_no_analysis(tmp_path: Path) -> None:
    """O11: a symlink is never followed (Annex B)."""
    (git_init(tmp_path) / "elsewhere.yaml").write_text(MINIMAL)
    (tmp_path / "astra.yaml").symlink_to("elsewhere.yaml")
    with pytest.raises(api.NoAnalysisError, match="no astra.yaml"):
        api.validate(tmp_path)


# --- astra-spec's examples, and §2's worked example ---


EXAMPLES = sorted(path.parent for path in (SPEC / "examples").glob("**/astra.yaml"))


def test_the_examples_are_found() -> None:
    assert len(EXAMPLES) == 4


@pytest.mark.parametrize("folder", EXAMPLES, ids=lambda path: path.relative_to(SPEC).as_posix())
def test_an_example_reports_no_problems(tmp_path: Path, folder: Path) -> None:
    shutil.copytree(SPEC / "examples", tmp_path / "examples")
    git_init(tmp_path)
    report = api.validate(tmp_path / folder.relative_to(SPEC))
    assert (report.diagnostics, len(report.unchecked)) == ((), 32)


WORKED_EXAMPLE = """\
spec_version: "0.1.0"
label: Example analysis

inputs:
  input1:
    path: data/input1.csv

decisions:
  decision1:
    rationale: Both are reasonable, and they may give different results.
    options:
      a: {}
      b: {}

outputs:
  output1:
    type: metric
    format: json
    inputs: [input1]
    decisions: [decision1]
    recipe:
      command: >-
        python src/output1.py '{inputs.input1}' '{decisions.decision1}'
        '{output}'
  output2:
    type: table
    format: csv
    inputs: [output1#u1, output1#u2]
    recipe:
      command: >-
        python src/output2.py '{inputs.output1#u1}' '{inputs.output1#u2}'
        '{output}'

universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: b}

findings:
  insight1:
    claim: Options a and b of decision1 give different results.
    evidence:
      - artifact: output2
"""


def test_the_worked_example_reports_no_problems(tmp_path: Path) -> None:
    """§2, whose pins `output1#u1` need no quotes."""
    assert checked_in_repository(tmp_path, WORKED_EXAMPLE).diagnostics == ()
