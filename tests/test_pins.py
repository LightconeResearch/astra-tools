"""§13 Pins, and outputs built per universe or once: which outputs are built per universe, and
`PIN_INACTIVE` and `INPUT_NOT_BUILT`, with Annex D cases 5, 6 and 7.

The stacks are §2's worked example with §9's `output4`, which is active only where `decision1.b`
is selected: a keeping one, whose `output6` reads `output4` only where it is active, and a
breaking one, with §13's `output4#u1` and an output planned in `u1` that reads `output4`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from astra import api
from astra.diagnostics import Catalogue
from astra.rules import pins
from astra.rules.context import Context
from astra.sources.git import Repository
from astra.sources.reader import WorktreeReader
from astra.stack import Element, Identity, bind
from tests.conftest import repository

ROOT = """\
spec_version: "0.1.0"
inputs:
  input1:
    path: data/input1.csv
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
  output2:
    type: table
    format: csv
    inputs: [output1#u1, output1#u2]
    recipe:
      command: python src/output2.py '{inputs.output1#u1}' '{inputs.output1#u2}' '{output}'
  output3:
    type: data
    format: csv
    inputs: [input1]
    recipe:
      command: python src/output3.py '{inputs.input1}' '{output}'
  output4:
    type: figure
    format: png
    when: [decision1.b]
    recipe:
      command: python src/output4.py '{output}'
  output6:
    type: table
    format: csv
    when: [decision1.b]
    inputs: [output4, output4#u2, input1#u1]
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: b}
"""
"""§2's worked example, §10's `output3` and §9's `output4`; `output6` reads `output4` only where
it is active, pinned to `u2`, where it is, and pins an input."""

KEPT = (
    ROOT + "findings:\n  insight1:\n    claim: Figure 4.\n    evidence: [{artifact: output4#u2}]\n"
)

BROKEN = (
    ROOT
    + """\
  u3:
    derived_from: u9
  u4:
    label: Selects nothing
findings:
  insight1:
    claim: Figure 4.
    evidence: [{artifact: output4#u1}]
"""
).replace(
    "universes:\n",
    """\
  output7:
    type: table
    format: csv
    inputs: [output4#u1, output4#u3, output4#u4, output4#u9]
    recipe:
      command: python make.py '{output}'
  output8:
    type: table
    format: csv
    inputs: [output4]
    recipe:
      command: python make.py '{output}'
universes:
""",
)
"""§13's `output4#u1`, in `inputs` and in evidence (§14), and `output8`, planned in `u1`, `u2`
and `u4`, reading `output4` without a pin; `u3` has no effective selection (Annex D case 7) and
`u4` leaves `decision1` unset, so `output4`'s activity there is undetermined (case 6); `u9`
names no universe (case 5)."""


def files(text: str) -> dict[str, str]:
    return {"astra.yaml": text, "data/input1.csv": "1\n"}


@pytest.fixture(scope="module")
def kept(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("kept"), files(KEPT))


@pytest.fixture(scope="module")
def broken(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("broken"), files(BROKEN))


def found(top: Path) -> list[tuple[str, str]]:
    report = api.validate(top)
    return [(d.code, d.location.pointer) for d in report.diagnostics if d.code in pins.CODES]


def test_outputs_built_per_universe_and_once(kept: Path) -> None:
    """§13 *Built per universe or built once*: `output1` lists `decisions`, `output4` has a
    `when`, and `output6` both and an unpinned entry naming `output4`; `output2` reads
    `output1` pinned to each universe, and `output3` reads only `input1`, so both are built
    once."""
    stack = bind(WorktreeReader(kept, Repository(kept)), "").stack
    assert stack is not None
    per_universe = Context(stack, Catalogue.load()).per_universe
    assert {element.id for element in per_universe} == {"output1", "output4", "output6"}
    assert Element(Identity(""), "output", "output2") not in per_universe


def test_a_stack_whose_pins_and_reads_are_active_keeps_both_rules(kept: Path) -> None:
    """§13 *Which universe a reference reads*: `output6` is planned only in `u2`, where
    `output4` is active, and pins it there; a pin on an input names a universe and changes
    nothing else."""
    assert found(kept) == []
    assert api.validate(kept).diagnostics == ()


def test_a_pinned_output_inactive_where_it_is_pinned_breaks_pin_inactive(broken: Path) -> None:
    """§13: where `output4` has `when: [decision1.b]`, `output4#u1` breaks `PIN_INACTIVE`, since
    `u1` selects `decision1: a`; evidence pins as `Output.inputs` does (§14). A pin naming a
    universe with no effective selection, or one where `output4`'s activity is undetermined,
    or naming no universe, isn't checked (Annex D cases 5, 6 and 7)."""
    pinned = [pointer for code, pointer in found(broken) if code == "PIN_INACTIVE"]
    assert pinned == ["/outputs/output7/inputs/0", "/findings/insight1/evidence/0/artifact"]
    message = next(d.message for d in api.validate(broken).diagnostics if d.code == "PIN_INACTIVE")
    assert "`output4#u1` pins `output4` to `u1`, where it isn't active" in message
    assert "`decision1.b`" in message


def test_an_unpinned_read_of_an_inactive_output_breaks_input_not_built(broken: Path) -> None:
    """§13: an output with a result planned in `u1` that reads `output4` without a pin breaks
    `INPUT_NOT_BUILT`, once, in `u1` alone: not in `u2`, where `output4` is active, nor in
    `u4`, where its activity is undetermined, nor in `u3`, which has no effective selection
    (Annex D cases 6 and 7)."""
    report = api.validate(broken)
    breaking = [d for d in report.diagnostics if d.code == "INPUT_NOT_BUILT"]
    assert [(d.level, d.location.pointer) for d in breaking] == [
        ("error", "/outputs/output8/inputs/0")
    ]
    assert "`output8` reads `output4` without a pin in `u1`, where it isn't active" in (
        breaking[0].message
    )
