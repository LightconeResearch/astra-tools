"""Pins, and outputs built per universe or once. `UNKNOWN_PIN_UNIVERSE` and `PIN_NOT_BUILT`
are tested with driving and switches.

The stack is the worked example with an `output3` built once, an `output4` built per universe,
and `output6`, which reads `output4` unpinned and pinned to `u2`, and pins an input.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from astra import api
from astra.diagnostics import Catalogue
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
    decisions: [decision1]
    recipe:
      command: python src/output4.py '{output}'
  output6:
    type: table
    format: csv
    inputs: [output4, output4#u2, input1#u1]
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: b}
"""
"""The worked example, an `output3` built once and an `output4` built per universe; `output6`
reads `output4` unpinned and pinned to `u2`, and pins an input."""

KEPT = (
    ROOT + "findings:\n  insight1:\n    claim: Figure 4.\n    evidence: [{artifact: output4#u2}]\n"
)


def files(text: str) -> dict[str, str]:
    return {"astra.yaml": text, "data/input1.csv": "1\n"}


@pytest.fixture(scope="module")
def kept(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("kept"), files(KEPT))


def test_outputs_built_per_universe_and_once(kept: Path) -> None:
    """`output1` and `output4` list `decisions`, and
    `output6` reads `output4` without a pin; `output2` reads `output1` pinned to each universe,
    and `output3` reads only `input1`, so both are built once."""
    stack = bind(WorktreeReader(kept, Repository(kept)), "").stack
    assert stack is not None
    per_universe = Context(stack, Catalogue.load()).per_universe
    assert {element.id for element in per_universe} == {"output1", "output4", "output6"}
    assert Element(Identity(""), "output", "output2") not in per_universe


def test_a_stack_whose_pins_name_universes_is_valid(kept: Path) -> None:
    """`output6` and the evidence pin `output4` to `u2`; a pin on an input
    names a universe and changes nothing else."""
    assert api.validate(kept).diagnostics == ()
