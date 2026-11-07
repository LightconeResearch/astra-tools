"""§10 Outputs: `AMBIGUOUS_ID` and `OUTPUT_CYCLE`, through any declaration, by identity (§15,
§17), with Annex D cases 4 and 5."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra import api
from tests.conftest import MINIMAL, repository


def outputs(reads: dict[str, str]) -> str:
    """`outputs:` with an output per entry, reading the flow list its value gives, if any."""
    text = "outputs:\n"
    for id_, inputs in reads.items():
        text += f"  {id_}:\n    type: data\n    format: csv\n"
        text += f"    inputs: {inputs}\n" if inputs else ""
        text += "    recipe:\n      command: python make.py '{inputs}' '{output}'\n"
    return text


def found(report: api.ValidationReport, code: str) -> list[tuple[str, str, str | None]]:
    return [
        (d.location.file, d.location.pointer, d.location.key)
        for d in report.diagnostics
        if d.code == code
    ]


# --- AMBIGUOUS_ID ---


def test_an_input_and_an_output_sharing_an_id_break_ambiguous_id(tmp_path: Path) -> None:
    """§6 *Ids and maps*, §10: `Output.inputs` takes both, whether or not an entry names the
    id; reported at the output, with the input related, in whichever file has both."""
    shared = 'spec_version: "0.1.0"\ninputs:\n  data1: {path: data1.csv}\n'
    files = {
        "astra.yaml": shared + "analyses: {sub: {path: sub}}\n" + outputs({"data1": ""}),
        "sub/astra.yaml": shared + outputs({"data1": "", "data2": "[data1]"}),
        "data1.csv": "1\n",
        "sub/data1.csv": "1\n",
    }
    report = api.validate(repository(tmp_path, files))
    assert found(report, "AMBIGUOUS_ID") == [
        ("astra.yaml", "/outputs", "data1"),
        ("sub/astra.yaml", "/outputs", "data1"),
    ]
    related = next(d for d in report.diagnostics if d.code == "AMBIGUOUS_ID").related
    assert [(r.pointer, r.key, r.line) for r in related] == [("/inputs", "data1", 3)]


def test_ids_of_other_kinds_or_analyses_may_be_the_same(tmp_path: Path) -> None:
    """§6 *Ids and maps*: a decision may share its id with an output, and an input of one
    analysis with an output of another."""
    root = MINIMAL + "analyses: {sub: {path: sub}}\ndecisions:\n  result: {options: {a: {}}}\n"
    sub = 'spec_version: "0.1.0"\n' + outputs({"data1": "[parent.data1]"})
    sub += "analyses: {parent: {path: ..}}\n"
    files = {
        "astra.yaml": root + "inputs:\n  data1: {path: data1.csv}\n",
        "sub/astra.yaml": sub,
        "data1.csv": "1\n",
    }
    assert found(api.validate(repository(tmp_path, files)), "AMBIGUOUS_ID") == []


# --- OUTPUT_CYCLE ---

CYCLES = 'spec_version: "0.1.0"\n' + outputs(
    {
        "alone": "[alone]",
        "first": "[second]",
        "second": "[input1, first]",
        "pinned": "[pinned#u1]",
        "through": "[again.lower]",
        "itself": "[self.itself]",
        "fine": "[first, nothere.x]",
        "hidden": "[bad.lower]",
    }
)
"""Outputs that depend on themselves: directly, through another, through a pin, through `sub`
under a second spelling and back through its `..`, and through `self: {path: .}`; and two that
don't, though one reads a cycle and the other reads into an undetermined analysis."""

LOWER = 'spec_version: "0.1.0"\nanalyses: {parent: {path: ..}}\n' + outputs(
    {"lower": "[parent.through, parent.input1]"}
)


@pytest.fixture(scope="module")
def cycles(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    root = (
        CYCLES
        + "inputs:\n  input1: {path: input1.csv}\n"
        + "analyses:\n  sub: {path: sub}\n  again: {path: ./sub}\n  self: {path: .}\n"
        + "  bad: {path: bad}\n"
        + "universes:\n  u1: {}\n"
    )
    bad = LOWER.replace("parent.through", "parent.hidden") + "name: x\n"
    files = {
        "astra.yaml": root,
        "input1.csv": "1\n",
        "sub/astra.yaml": LOWER,
        "bad/astra.yaml": bad,
    }
    return api.validate(repository(tmp_path_factory.mktemp("cycles"), files))


def test_an_output_depending_on_itself_breaks_output_cycle(cycles: api.ValidationReport) -> None:
    """§10, §15 *One analysis, however it is declared*: reported at each entry of `inputs` on a
    cycle, in each file the cycle goes through, pinned or not, whatever the spelling."""
    assert found(cycles, "OUTPUT_CYCLE") == [
        ("astra.yaml", "/outputs/alone/inputs/0", None),
        ("astra.yaml", "/outputs/first/inputs/0", None),
        ("astra.yaml", "/outputs/second/inputs/1", None),
        ("astra.yaml", "/outputs/pinned/inputs/0", None),
        ("astra.yaml", "/outputs/through/inputs/0", None),
        ("astra.yaml", "/outputs/itself/inputs/0", None),
        ("sub/astra.yaml", "/outputs/lower/inputs/0", None),
    ]
    message = next(d.message for d in cycles.diagnostics if "/through/" in d.location.pointer)
    assert message.endswith("`through` → `lower` of `sub` → `through`")


def test_an_output_on_no_cycle_keeps_it(cycles: api.ValidationReport) -> None:
    """§10: `fine` reads an output on a cycle, and isn't on it; Annex D case 5: `nothere.x`
    names nothing; case 4: `bad`'s `lower` would lead back to `hidden`, but `bad` is
    undetermined, so nothing through it is checked."""
    pointers = [pointer for _, pointer, _ in found(cycles, "OUTPUT_CYCLE")]
    assert not any("/fine/" in pointer or "/hidden/" in pointer for pointer in pointers)
    in_bad = [d.code for d in cycles.diagnostics if d.location.file == "bad/astra.yaml"]
    assert in_bad == ["UNKNOWN_FIELD"]


def test_outputs_reading_others_in_order_keep_it(tmp_path: Path) -> None:
    """§2's worked example, whose `output2` reads `output1` pinned to two universes, and a
    stage reading its parent's input through `..`."""
    root = 'spec_version: "0.1.0"\n' + outputs(
        {"output1": "[sub.lower]", "output2": "[output1#u1, output1#u2]", "output3": "[output1]"}
    )
    root += "analyses: {sub: {path: sub}}\ninputs:\n  input1: {path: input1.csv}\n"
    root += "universes:\n  u1: {}\n  u2: {}\n"
    lower = LOWER.replace("parent.through, ", "")
    files = {"astra.yaml": root, "input1.csv": "1\n", "sub/astra.yaml": lower}
    assert found(api.validate(repository(tmp_path, files)), "OUTPUT_CYCLE") == []
