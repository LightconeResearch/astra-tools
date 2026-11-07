"""§16 *The universe being built* and §18 *Results and where they go*: the universes built,
what is built in each, and the root's planned results, over which §16's rules hold, each with
its names.

The stacks are §2's worked example; §16's `output5` reading §15's `subanalysis` in the root's
`u1` and in `subanalysis`'s own `u1` and `v1`, where `v1` drives its parent through
`parent: {path: ..}` (§18); and §16's `stage.lib.out#v1`, read through two declarations.
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
from astra.universes import Building
from tests.conftest import repository
from tests.test_validate import WORKED_EXAMPLE

SUBANALYSIS = """\
spec_version: "0.1.0"
analyses:
  parent: {path: ..}
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
  unread:
    type: metric
    format: json
    decisions: [decision1]
    recipe:
      command: python src/unread.py '{decisions.decision1}' '{output}'
universes:
  u1:
    decisions: {decision1: a, parent.decision1: b}
  v1:
    decisions: {decision1: b, parent.decision1: a}
"""
"""§15's `subanalysis`, whose own universes drive its parent (§18), and an output nothing
reads."""

ROOT = """\
spec_version: "0.1.0"
analyses:
  subanalysis: {path: subanalysis}
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    inputs: [input1, subanalysis.output1]
    decisions: [decision1]
    recipe:
      command: >-
        python src/output1.py '{inputs.input1}' '{inputs.subanalysis.output1}'
        '{decisions.decision1}' '{output}'
  output4:
    type: figure
    format: png
    when: [decision1.b]
    recipe:
      command: python src/output4.py '{output}'
  output5:
    type: table
    format: csv
    inputs:
      - subanalysis.output1#u1               # the root's u1
      - subanalysis.output1#subanalysis_u1   # subanalysis's own u1, imported
      - subanalysis.output1#v1               # subanalysis's own v1
      - output1#subanalysis_v1               # the root's output1, as subanalysis's v1 builds it
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a, subanalysis.decision1: a}
  u2:
    decisions: {decision1: b, subanalysis.decision1: b}
  subanalysis_u1: {analysis: subanalysis, universe: u1}
  subanalysis_v1: {analysis: subanalysis, universe: v1}
findings:
  insight1:
    claim: The decision of subanalysis changes its output.
    evidence: [{artifact: subanalysis.output1}]
"""
"""§16's `output5`, §9's `output4`, and a finding citing `subanalysis.output1` without a pin."""

ROOT_ID, SUB_ID = Identity(""), Identity("subanalysis")


def building(top: Path) -> Building:
    stack = bind(WorktreeReader(top, Repository(top)), "").stack
    assert stack is not None
    return Context(stack, Catalogue.load()).building


def planned(top: Path) -> set[tuple[str, str]]:
    """Each planned result, for each of its names: the analysis it is named from, the universe's
    for a result built in a universe and else its output's, and the name, followed by `#` and
    the universe's own id for a result built in a universe (§18)."""
    return {
        (str(result.output.analysis), name)
        if result.universe is None
        else (str(result.universe.analysis), f"{name}#{result.universe.id}")
        for result in building(top).planned.values()
        for name in result.names
    }


@pytest.fixture(scope="module")
def worked(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {"astra.yaml": WORKED_EXAMPLE, "data/input1.csv": "1\n"}
    return repository(tmp_path_factory.mktemp("worked"), files)


@pytest.fixture(scope="module")
def pinning(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {
        "astra.yaml": ROOT,
        "data/input1.csv": "1\n",
        "subanalysis/astra.yaml": SUBANALYSIS,
        "subanalysis/data/input1.csv": "2\n",
    }
    return repository(tmp_path_factory.mktemp("pinning"), files)


def test_the_worked_example_plans_its_three_results(worked: Path) -> None:
    """§2 and §18: `output1`'s results in `u1` and in `u2`, and `output2`'s, built once, each
    named by its output's id; `output2` and the finding citing it add none."""
    found = building(worked)
    assert [
        (r.output.id, r.universe and r.universe.id, r.names) for r in found.planned.values()
    ] == [
        ("output1", "u1", ("output1",)),
        ("output1", "u2", ("output1",)),
        ("output2", None, ("output2",)),
    ]
    assert planned(worked) == {(".", "output1#u1"), (".", "output1#u2"), (".", "output2")}
    assert list(found.universes) == [
        Element(ROOT_ID, "universe", "u1"),
        Element(ROOT_ID, "universe", "u2"),
    ]


def test_the_universes_built_are_the_roots_and_those_pins_name(pinning: Path) -> None:
    """§16 *The universe being built*: the root's universes, and those a pin on an output built
    per universe names in a planned result's `inputs`: `subanalysis`'s own `u1`, through the
    import, and `v1`, with no entry `v1` in the root's file. In each, its own analysis is the
    driver, and is built with what its universes drive: the root's drive `subanalysis`, and
    `subanalysis`'s `v1` drives its parent."""
    universes = building(pinning).universes
    assert {(str(u.analysis), u.id): list(built) for u, built in universes.items()} == {
        (".", "u1"): [ROOT_ID, SUB_ID],
        (".", "u2"): [ROOT_ID, SUB_ID],
        ("subanalysis", "u1"): [SUB_ID, ROOT_ID],
        ("subanalysis", "v1"): [SUB_ID, ROOT_ID],
    }


def test_each_planned_result_is_named_from_the_analysis_whose_universe_it_is_built_in(
    pinning: Path,
) -> None:
    """§18: the root's outputs in its universes where they are active (`output4` only in
    `u2`), `output5` once; what the root builds of `subanalysis` in its universes is named
    `subanalysis.output1`; `output1` in `subanalysis`'s own `u1` and `v1` is named from
    `subanalysis`; the root's `output1`, built in `v1` through the driven `parent: {path: ..}`,
    is named `parent.output1` there, though the root's own file reads it as
    `output1#subanalysis_v1`. The finding cites `subanalysis.output1` in each of the root's
    universes (§20 *Evidence*); `unread`, which nothing reads or cites, isn't planned."""
    assert planned(pinning) == {
        (".", "output1#u1"),
        (".", "output1#u2"),
        (".", "output4#u2"),
        (".", "output5"),
        (".", "subanalysis.output1#u1"),
        (".", "subanalysis.output1#u2"),
        ("subanalysis", "output1#u1"),
        ("subanalysis", "output1#v1"),
        ("subanalysis", "parent.output1#v1"),
    }


def test_a_stack_read_in_its_own_universes_and_anothers_validates(pinning: Path) -> None:
    """§16 *Pins and imported universes*: every pin of `output5` reads a universe where the
    analysis it reads is built, and the undriven `parent` adds no name in the root's
    universes (§18)."""
    assert api.validate(pinning).diagnostics == ()


LIB = """\
spec_version: "0.1.0"
analyses:
  parent: {path: ..}
outputs:
  out:
    type: metric
    format: json
    decisions: [parent.d]
    recipe:
      command: python make.py '{decisions.parent.d}' '{output}'
universes:
  v1: {}
"""
"""`stage`'s `lib`, with no decisions, whose `out` consumes `stage`'s `d`, and a `v1` of its own
that drives nothing."""

STAGE = """\
spec_version: "0.1.0"
analyses:
  lib: {path: lib}
decisions:
  d:
    options: {a: {}, b: {}}
outputs:
  stage_out:
    type: metric
    format: json
    decisions: [d]
    recipe:
      command: python make.py '{decisions.d}' '{output}'
universes:
  v1:
    decisions: {d: a}
"""
"""§16's `stage`, whose universes drive `lib`, since it has no decisions."""

READING_LIB = """\
spec_version: "0.1.0"
analyses:
  stage: {path: stage}
outputs:
  compared:
    type: table
    format: csv
    inputs:
      - stage.lib.out#v1              # lib's own v1
      - stage.lib.out#stage_v1        # stage's own v1, imported
      - stage.stage_out#lib_v1        # NOT_BUILT_IN_UNIVERSE
    recipe:
      command: python make.py '{output}'
universes:
  stage_v1: {analysis: stage, universe: v1}
  lib_v1: {analysis: stage.lib, universe: v1}
"""
"""A root with no universes of its own, reading §16's `stage.lib.out` in two universes."""


@pytest.fixture(scope="module")
def reading_lib(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {"astra.yaml": READING_LIB, "stage/astra.yaml": STAGE, "stage/lib/astra.yaml": LIB}
    return repository(tmp_path_factory.mktemp("reading_lib"), files)


def test_a_pin_names_a_universe_of_the_analysis_whose_element_it_reads(
    reading_lib: Path,
) -> None:
    """§16 *Pins and imported universes*: in a file with no `v1`, `stage.lib.out#v1` names
    `lib`'s `v1`, since `out` is `lib`'s output, and through the import
    `stage_v1: {analysis: stage, universe: v1}`, `stage.lib.out#stage_v1` reads `out` as
    `stage` builds it in its own `v1`, where its universes drive `lib`: so it is named
    `lib.out` there (§18)."""
    lib, stage = Identity("stage/lib"), Identity("stage")
    out = Element(lib, "output", "out")
    assert [(key, result.names) for key, result in building(reading_lib).planned.items()] == [
        ((Element(ROOT_ID, "output", "compared"), None), ("compared",)),
        ((out, Element(lib, "universe", "v1")), ("out",)),
        ((out, Element(stage, "universe", "v1")), ("lib.out",)),
    ]


def test_a_pin_to_another_analysiss_universe_is_held_by_the_first_rule_alone(
    reading_lib: Path,
) -> None:
    """§16: a pin that names another analysis's universe is not in the driver's file, so only
    rule 1 holds it. The root's universes drive nothing, yet its pins through `stage.lib` break
    no rule; `stage.stage_out#lib_v1` breaks NOT_BUILT_IN_UNIVERSE alone, since `lib`'s `v1`
    doesn't build `stage`. In `lib`'s own `v1`, which doesn't drive `parent`, `lib`'s `out`
    consumes `parent.d` where `stage` isn't built, in the file of the analysis whose universe
    it is: both rules."""
    report = api.validate(reading_lib)
    assert [(d.code, d.location.file, d.location.pointer) for d in report.diagnostics] == [
        ("NOT_BUILT_IN_UNIVERSE", "astra.yaml", "/outputs/compared/inputs/2"),
        ("NOT_BUILT_IN_UNIVERSE", "stage/lib/astra.yaml", "/outputs/out/decisions/0"),
        ("UNDRIVEN_DECLARATION", "stage/lib/astra.yaml", "/outputs/out/decisions/0"),
    ]
