"""§16's rules on the universe being built, `NOT_BUILT_IN_UNIVERSE` and `UNDRIVEN_DECLARATION`,
and `RESULT_IN_TWO_PLACES` (§16, §18), with design §4.13 cases 5 and 7.

The stacks are §16's: the root drives §15's `subanalysis`, which consumes the root's `decision1`
through `parent: {path: ..}`, and `stage`, which declares `inner` and a second `inner_undriven`
of one folder; `other` is never driven, and has a universe `v1` of its own. The breaking stack
adds §16's `undriven: {path: subanalysis}`, `stage_undriven: {path: stage}` and a root `inner`
that keys drive beside `stage.inner` (§18). The last stack is §17's `previous`, the analysis's
own folder at an earlier commit.
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
from tests.conftest import git, repository

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
    decisions: [decision1, parent.decision1]
    recipe:
      command: python make.py '{decisions.decision1}' '{decisions.parent.decision1}' '{output}'
"""
"""§15's `subanalysis`, which consumes its parent's `decision1` (§16 *The universe being built*)."""

INNER = """\
spec_version: "0.1.0"
decisions:
  d:
    options: {a: {}, b: {}}
outputs:
  out:
    type: metric
    format: json
    decisions: [d]
    recipe:
      command: python make.py '{decisions.d}' '{output}'
"""

OTHER = """\
spec_version: "0.1.0"
decisions:
  d:
    options: {a: {}, b: {}}
outputs:
  other_out:
    type: metric
    format: json
    decisions: [d]
    recipe:
      command: python make.py '{decisions.d}' '{output}'
universes:
  v1:
    decisions: {d: a}
"""
"""An analysis no key of the root's universes drives, with a universe of its own."""

STAGE = """\
spec_version: "0.1.0"
analyses:
  inner: {path: inner}
  inner_undriven: {path: inner}
  other: {path: ../other}
decisions:
  d:
    options: {a: {}, b: {}}
outputs:
  stage_out:
    type: metric
    format: json
    inputs: [inner.out]
    decisions: [d]
    recipe:
      command: python make.py '{output}'
"""
"""§16's `stage`, with `inner` declared twice."""

BROKEN_STAGE = (
    STAGE
    + """\
  stage_other:
    type: metric
    format: json
    inputs: [other.other_out]
    decisions: [other.d]
    recipe:
      command: python make.py '{output}'
"""
)
"""`stage`, listing a decision of `other` and reading its output, where `other` isn't built."""

ROOT = """\
spec_version: "0.1.0"
analyses:
  subanalysis: {path: subanalysis}
  stage: {path: stage}
  other: {path: other}
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  output6:
    type: metric
    format: json
    inputs:
      - subanalysis.output1
      - subanalysis.output1#u1
      - stage.inner.out
      - stage.stage_out
      - other.other_out#v1
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a, subanalysis.decision1: a, stage.d: a, stage.inner.d: a}
  u2:
    decisions: {decision1: b, subanalysis.decision1: b, stage.d: b, stage.inner.d: b}
"""
"""Reads through declarations the root's universes drive, and `other`'s output in its own
`v1`."""

BROKEN_ROOT = (
    ROOT.replace(
        "  other: {path: other}\n",
        """\
  other: {path: other}
  undriven: {path: subanalysis}
  stage_undriven: {path: stage}
  inner: {path: stage/inner}
""",
    )
    .replace(
        "    options: {a: {}, b: {}}\noutputs:\n",
        """\
    options:
      a: {incompatible_with: [other.d.b]}
      b: {}
outputs:
""",
    )
    .replace(
        "universes:\n",
        """\
  output7:
    type: metric
    format: json
    inputs:
      - undriven.output1           # UNDRIVEN_DECLARATION
      - undriven.output1#u1        # UNDRIVEN_DECLARATION
      - stage.inner_undriven.out
      - stage_undriven.inner.out
      - other.other_out
      - other.other_out#u1
      - stage.stage_other
    decisions: [other.d]
    recipe:
      command: python make.py '{output}'
  output8:
    type: metric
    format: json
    inputs: [nothere.output1]
    recipe:
      command: python make.py '{output}'
universes:
""",
    )
    + """\
  u3:
    decisions: {decision1: a, subanalysis.decision1: a, stage.d: a, inner.d: a}
  u4:
    derived_from: u9
"""
)
"""§16's reads through undriven declarations, uses of `other`'s output and decision in the
root's universes, in each place a use can be written, and `u3`'s key `inner.d`, which drives the
root's `inner` beside `stage.inner` (§18). `output8` reads through `nothere`, which names nothing
(design §4.13 case 5), and `u4` has no effective selection (case 7)."""


def files(root: str, stage: str) -> dict[str, str]:
    return {
        "astra.yaml": root,
        "subanalysis/astra.yaml": SUBANALYSIS,
        "subanalysis/data/input1.csv": "1\n",
        "stage/astra.yaml": stage,
        "stage/inner/astra.yaml": INNER,
        "other/astra.yaml": OTHER,
    }


@pytest.fixture(scope="module")
def kept(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    return api.validate(repository(tmp_path_factory.mktemp("kept"), files(ROOT, STAGE)))


@pytest.fixture(scope="module")
def broken(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    top = repository(tmp_path_factory.mktemp("broken"), files(BROKEN_ROOT, BROKEN_STAGE))
    return api.validate(top)


def found(report: api.ValidationReport, code: str) -> list[tuple[str, str]]:
    return [(d.location.file, d.location.pointer) for d in report.diagnostics if d.code == code]


def test_reads_through_driven_declarations_keep_both_rules(kept: api.ValidationReport) -> None:
    """§16: the root's universes drive `subanalysis`, `stage` and `stage.inner`, so its
    `output6` reads their outputs built per universe without a pin, or pinned to `u1`; it reads
    `other`'s in `other`'s own `v1`, where `other` is the driver; and `subanalysis` consumes
    the root's `decision1` as `parent.decision1`, since the analysis whose universe is being
    built is always built in it (§16 *The universe being built*)."""
    assert kept.diagnostics == ()


def test_a_read_through_an_undriven_declaration_breaks_undriven_declaration(
    broken: api.ValidationReport,
) -> None:
    """§16 *A second declaration of one folder*: `undriven.output1` and `undriven.output1#u1`
    break it, though `subanalysis`'s folder is driven through `subanalysis`; so do
    `stage.inner_undriven.out`, though the root drives `stage`, and `stage_undriven.inner.out`,
    though it drives `stage.inner`. Each is built in the root's universes, so
    `NOT_BUILT_IN_UNIVERSE` holds."""
    reads = {("astra.yaml", f"/outputs/output7/inputs/{index}") for index in range(4)}
    assert reads <= set(found(broken, "UNDRIVEN_DECLARATION"))
    assert not reads & set(found(broken, "NOT_BUILT_IN_UNIVERSE"))
    messages = {d.location.pointer: d.message for d in broken.diagnostics}
    assert (
        "through `stage.inner_undriven`, which this file's universes don't"
        in (messages["/outputs/output7/inputs/2"])
    )
    assert "through `stage_undriven`, which" in messages["/outputs/output7/inputs/3"]


def test_each_use_of_an_analysis_not_built_breaks_both_rules_in_the_drivers_file(
    broken: api.ValidationReport,
) -> None:
    """§16 *The universe being built*: `other` isn't built in the root's universes, so in the
    root's file its output read without a pin or pinned to `u1`, and its decision listed by a
    planned result's output, break both rules; in `stage`'s file, where `stage_other` reads its
    output and lists its decision, NOT_BUILT_IN_UNIVERSE alone holds them. Reads through driven
    declarations, `other`'s output in its own `v1`, and the root's constraint naming `other`'s
    decision, which uses nothing (Rules), break neither."""
    uses = [
        ("astra.yaml", "/outputs/output7/inputs/4"),
        ("astra.yaml", "/outputs/output7/inputs/5"),
        ("astra.yaml", "/outputs/output7/decisions/0"),
    ]
    in_stage = [
        ("stage/astra.yaml", "/outputs/stage_other/inputs/0"),
        ("stage/astra.yaml", "/outputs/stage_other/decisions/0"),
    ]
    assert found(broken, "NOT_BUILT_IN_UNIVERSE") == uses + in_stage
    reads = [("astra.yaml", f"/outputs/output7/inputs/{index}") for index in range(4)]
    assert sorted(found(broken, "UNDRIVEN_DECLARATION")) == sorted(uses + reads)
    message = next(
        d.message
        for d in broken.diagnostics
        if d.code == "NOT_BUILT_IN_UNIVERSE" and d.location.pointer == "/outputs/output7/inputs/4"
    )
    assert "reads an output of `other` in `u1`, `u2` and `u3`, where that analysis" in message
    in_stage = next(d.message for d in broken.diagnostics if d.location.file == "stage/astra.yaml")
    assert "in `u1`, `u2` and `u3` of `.`, where" in in_stage


def test_a_result_reached_through_two_driven_chains_breaks_result_in_two_places(
    broken: api.ValidationReport,
) -> None:
    """§18: keys go through the root's `inner` and `stage.inner`, so `inner`'s `out`, planned in
    each of the root's universes, has two names; it is reported, as a warning, at the root's
    `inner` and `stage`, each with the other as a related place. Driven through `stage.inner`
    alone, as in the keeping stack, it has one."""
    two = [d for d in broken.diagnostics if d.code == "RESULT_IN_TWO_PLACES"]
    assert [(d.level, d.location.file, d.location.pointer) for d in two] == [
        ("warning", "astra.yaml", "/analyses/stage"),
        ("warning", "astra.yaml", "/analyses/inner"),
    ]
    assert [[r.pointer for r in d.related] for d in two] == [
        ["/analyses/inner"],
        ["/analyses/stage"],
    ]
    assert "`out` in `u1`, `u2` and `u3` has two names, `stage.inner.out` and `inner.out`" in (
        two[0].message
    )


def test_nothing_is_checked_where_annex_d_leaves_it_undetermined(
    broken: api.ValidationReport,
) -> None:
    """design §4.13: no rule on the universe being built in `u4`, which has no effective selection
    (case 7), nor through `nothere`, which names nothing (case 5)."""
    ours = [
        d for d in broken.diagnostics if d.code in ("NOT_BUILT_IN_UNIVERSE", "UNDRIVEN_DECLARATION")
    ]
    assert not [d for d in ours if "`u4`" in d.message]
    assert not [d for d in ours if d.location.pointer.startswith("/outputs/output8/inputs/")]
    assert [
        d.code for d in broken.diagnostics if d.location.pointer == "/outputs/output8/inputs/0"
    ] == ["UNRESOLVED_ADDRESS"]


PREVIOUS = """\
spec_version: "0.1.0"
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
    decisions: {decision1: a}
"""
"""The analysis as it was at an earlier commit, with a `u1` of its own."""

COMPARED = """\
  compared:
    type: table
    format: csv
    inputs:
      - output1#u1
      - previous.output1#u1           # UNDRIVEN_DECLARATION, NOT_BUILT_IN_UNIVERSE
      - previous.output1#previous_u1
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a}
  previous_u1:                 # previous's own u1, imported
    analysis: previous
    universe: u1
"""


def test_an_earlier_commits_result_is_read_through_an_import(tmp_path: Path) -> None:
    """§17 *Using one*: where `previous` names the analysis's own folder at a commit and both
    have a `u1`, `previous.output1#u1` names the analysis's own `u1`, which doesn't build
    `previous`, so it breaks `UNDRIVEN_DECLARATION` and `NOT_BUILT_IN_UNIVERSE`, and plans
    nothing more (design §4.13 case 12); with the import, `previous.output1#previous_u1` reads
    `output1` in `previous`'s own `u1`."""
    top = repository(tmp_path, {"astra.yaml": PREVIOUS, "data/input1.csv": "1\n"})
    commit = git(top, "rev-parse", "HEAD").strip()
    declared = f"analyses:\n  previous:\n    path: .\n    commit: {commit}\ninputs:\n"
    later = PREVIOUS.replace("inputs:\n", declared, 1).split("universes:\n")[0] + COMPARED
    repository(top, {"astra.yaml": later})
    report = api.validate(top)
    pinned = [(d.code, d.location.pointer) for d in report.diagnostics]
    assert pinned == [
        ("NOT_BUILT_IN_UNIVERSE", "/outputs/compared/inputs/1"),
        ("UNDRIVEN_DECLARATION", "/outputs/compared/inputs/1"),
    ]
    stack = bind(WorktreeReader(top, Repository(top)), "").stack
    assert stack is not None
    planned = Context(stack, Catalogue.load()).building.planned
    assert list(planned) == [
        (Element(Identity(""), "output", "output1"), Element(Identity(""), "universe", "u1")),
        (Element(Identity(""), "output", "compared"), None),
        (
            Element(Identity("", commit), "output", "output1"),
            Element(Identity("", commit), "universe", "u1"),
        ),
    ]
