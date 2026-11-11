"""§11 Recipes: `UNDECLARED_TEMPLATE_REF`, the command read from the left as *The command as a
template* says, `{{` and `}}` included."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra import api
from tests.conftest import repository

SUB = """\
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


def analysis(commands: dict[str, str]) -> str:
    """The root, with an output per entry of `commands`, each reading the same entries."""
    text = (
        'spec_version: "0.1.0"\nanalyses:\n  subanalysis: {path: sub}\n'
        "inputs:\n  input1: {path: input1.csv}\n"
        "decisions:\n  decision1:\n    options: {a: {}, b: {}}\n"
        "universes:\n  u1:\n    decisions: {decision1: a, subanalysis.decision1: a}\n"
        "outputs:\n"
        "  output0:\n    type: metric\n    format: json\n"
        "    recipe: {command: \"python make.py '{output}'\"}\n"
    )
    for id_, command in commands.items():
        decisions = "" if id_.startswith("once") else "    decisions: [decision1]\n"
        text += (
            f"  {id_}:\n    type: metric\n    format: json\n"
            "    inputs: [input1, subanalysis.output1, output0#u1]\n"
            f"{decisions}    recipe:\n      command: {command!r}\n"
        )
    return text


def broken(report: api.ValidationReport) -> list[str]:
    return [d.location.pointer for d in report.diagnostics if d.code == "UNDECLARED_TEMPLATE_REF"]


BREAKING = {
    "unlisted": "python make.py '{inputs.input2}' '{output}'",
    "other_form": "python make.py {foo} '{output}'",
    "stray_close": "echo }",
    "never_ends": "python make.py '{output' --flag",
    "respelled": "python make.py '{inputs.again.output1}' '{output}'",
    "unpinned": "python make.py '{inputs.output0}' '{output}'",
    "near_miss": "python make.py '{input}' '{decision.decision1}' '{output}'",
    "literal_first": "python make.py {{inputs} '{output}'",
    "inside": "python make.py '{inputs.{input1}' '{output}'",
    "once_decided": "python make.py '{decisions.decision1}' '{output}'",
}
"""§11's examples of a placeholder naming an entry the output doesn't list, one of none of the
forms, and a stray brace; an entry not as written, its spelling or its pin changed; `{{`
read first from the left, leaving a stray `}`; a placeholder ending at the next `}`, a `{`
inside it; and a `{decisions.<entry>}` in an output that lists no decisions (§11 *The command as
a template*)."""


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    files = {"astra.yaml": analysis(BREAKING), "input1.csv": "1\n", "sub/astra.yaml": SUB}
    return api.validate(repository(tmp_path_factory.mktemp("recipes"), files))


def test_every_brace_outside_a_placeholder_it_gives_breaks_it(
    report: api.ValidationReport,
) -> None:
    """§11 *The command as a template*: one report for each placeholder or stray brace, at the
    command; `{input}` and `{decision.decision1}` are two."""
    assert broken(report) == [
        f"/outputs/{id_}/recipe/command"
        for id_ in BREAKING
        for _ in range(2 if id_ == "near_miss" else 1)
    ]


def test_it_says_which_brace_or_placeholder(report: api.ValidationReport) -> None:
    messages = {
        d.location.pointer.split("/")[2]: d.message
        for d in report.diagnostics
        if d.code == "UNDECLARED_TEMPLATE_REF"
    }
    assert "`{inputs.input2}`" in messages["unlisted"]
    assert "`}` at character 6" in messages["stray_close"]
    assert "`{` at character 17" in messages["never_ends"]
    assert "`{inputs.{input1}`" in messages["inside"]


KEEPING = {
    "every_form": (
        "python make.py '{inputs.input1}' '{inputs.subanalysis.output1}'"
        " '{inputs.output0#u1}' '{decisions.decision1}' '{output}'"
    ),
    "all_inputs": "python make.py {inputs} > '{output}'",
    "literals": "awk '{{print $1}}' '{inputs.input1}' > '{output}'; echo ${{HOME}} }}{{",
    "once_plain": "python make.py '{inputs.input1}' '{output}'",
}
"""§11's table and example, `{inputs}`, and `{{` and `}}` as literal braces."""


def test_placeholders_the_output_gives_keep_it(tmp_path: Path) -> None:
    """§11's table: `{inputs.<entry>}` and `{decisions.<entry>}` for each entry as written, dots
    and `#` included, `{inputs}` and `{output}`. A switch has no recipe to check (Elements
    *switch*)."""
    switch = "  switch1:\n    switch: decision1\n    cases: {a: output0, b: input1}\n"
    files = {"astra.yaml": analysis(KEEPING) + switch, "input1.csv": "1\n", "sub/astra.yaml": SUB}
    assert broken(api.validate(repository(tmp_path, files))) == []
