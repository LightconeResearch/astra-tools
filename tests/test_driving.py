"""§16 Driving and consuming, the rules on selections: which declarations are driven, and
`DUPLICATE_ELEMENT`, `LOOPING_KEY`, `MISSING_DECISION` and `UNKNOWN_PIN_UNIVERSE`, with design §4.13
cases 4, 5 and 10; and the universe each pin and import names.

The first stacks are §16's `stage`, which declares `inner`, `again: {path: .}` and
`parent: {path: ..}`, with the root declaring `inner` a second time: a keeping one, whose keys
spell `stage.inner.d` and `inner.d`, and a breaking one. The last is §16's `output5`, with §12's
import `subanalysis_v1`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from astra import api, rules
from astra.diagnostics import Catalogue
from astra.rules.context import Context
from astra.sources.git import Repository
from astra.sources.reader import WorktreeReader
from astra.stack import Element, Identity, Stack, bind
from astra.universes import Chain, built, imports, pins
from tests.conftest import SPEC, repository

OUTPUT = """\
outputs:
  %s:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
"""

INNER = (
    """spec_version: "0.1.0"
decisions:
  d:
    options: {a: {}, b: {}}
"""
    + OUTPUT % "inner_result"
)

STAGE = (
    """spec_version: "0.1.0"
analyses:
  inner: {path: inner}
  again: {path: .}
  parent: {path: ..}
decisions:
  d:
    options:
      a: {}
      b: {}
      c: {excluded: It isn't what stage is for.}
"""
    + (OUTPUT % "stage_result").replace(
        "    recipe:", "    decisions: [d, inner.d, parent.decision1]\n    recipe:"
    )
    + """\
universes:
  s1:
    decisions: {d: a, inner.d: a, parent.decision1: a}
"""
)
"""§16's `stage`: its universes drive `inner` and, through `..`, the root; `stage_result` lists
the decisions they set, so each universe uses each key (Results *uses*)."""

LIB = (
    """spec_version: "0.1.0"
analyses:
  deep: {path: deep}
  parent: {path: ..}
"""
    + OUTPUT % "lib_result"
)
"""An analysis with no decisions, which declares another and its parent."""

ROOT = (
    """spec_version: "0.1.0"
analyses:
  stage: {path: stage}
  stage2: {path: stage}
  inner: {path: stage/inner}
  lib: {path: lib}
  self: {path: .}
  bad: {path: bad}
decisions:
  decision1:
    options: {a: {}, b: {}}
"""
    + (OUTPUT % "result").replace(
        "    recipe:", "    decisions: [decision1, stage.d, stage.inner.d]\n    recipe:"
    )
    + """\
universes:
  u1:
    decisions: {decision1: a, stage.d: a, stage.inner.d: a}
  u2:
    decisions: {decision1: b, stage.d: a, inner.d: b}
  u3:
    derived_from: u1
    decisions: {stage.inner.d: b}
"""
)

KEPT_FILES = {
    "astra.yaml": ROOT.replace("  bad: {path: bad}\n", ""),
    "stage/astra.yaml": STAGE,
    "stage/inner/astra.yaml": INNER,
    "lib/astra.yaml": LIB,
    "lib/deep/astra.yaml": 'spec_version: "0.1.0"\n' + OUTPUT % "deep_result",
}

BROKEN_FILES = {
    **KEPT_FILES,
    "astra.yaml": ROOT
    + """\
  two_keys:
    decisions: {decision1: a, stage.d: a, stage.inner.d: a, inner.d: a}
  other_key:
    derived_from: u1
    decisions: {inner.d: b}
  again:
    decisions: {decision1: a, stage2.again.d: c, stage.inner.d: a}
  parent:
    decisions: {stage.d: a, stage.inner.d: a, stage.parent.decision1: a}
  itself:
    decisions: {self.decision1: a, stage.d: a, stage.inner.d: a}
  unset:
    decisions: {decision1: b}
  through_bad:
    decisions: {decision1: a, stage.d: a, stage.inner.d: a, bad.parent.decision1: a}
  through_nothing:
    decisions: {decision1: a, stage.d: a, stage.inner.d: a, stage.nothere.parent.decision1: a}
""",
    "stage/astra.yaml": STAGE
    + """\
  s2:
    decisions: {inner.d: a, parent.decision1: a}
  s3:
    decisions: {d: a, inner.d: a}
""",
    "bad/astra.yaml": LIB + "name: not a field\n",
}

CHECKED = rules.universes.CODES | rules.driving.CODES
"""The codes of §12's and §16's rules on selections."""

ROOT_ID = Identity("")


def found(report: api.ValidationReport) -> list[tuple[str, str, str, str | None]]:
    return [
        (d.code, d.location.file, d.location.pointer, d.location.key)
        for d in report.diagnostics
        if d.code in CHECKED
    ]


def bound(top: Path, folder: str = "") -> Stack:
    stack = bind(WorktreeReader(top, Repository(top)), folder).stack
    assert stack is not None
    return stack


def driven(stack: Stack) -> dict[Identity, tuple[Chain, ...]]:
    """The chains each analysis's universes drive (§16), given what they use (Results *uses*)."""
    return dict(Context(stack, Catalogue.load()).driven)


def chains(stack: Stack, identity: Identity = ROOT_ID) -> set[tuple[str, ...]]:
    return {tuple(d.id for d in chain) for chain in driven(stack)[identity]}


@pytest.fixture(scope="module")
def kept(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("kept"), KEPT_FILES)


@pytest.fixture(scope="module")
def broken(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("broken"), BROKEN_FILES)


@pytest.fixture(scope="module")
def broken_report(broken: Path) -> api.ValidationReport:
    return api.validate(broken)


# --- §16 *Which declarations are driven* ---


def test_each_chain_a_key_goes_through_is_driven_on_its_own(kept: Path) -> None:
    """§16: `stage.inner.d` drives `stage` and, through it, `stage`'s `inner`, and `inner.d`
    the root's own `inner`; `lib`, with no decisions, is driven whenever the driver's file
    declares it, and so is its `deep`, but not its `..`, which leads back; nor `self`, `stage2`
    or `stage`'s `again`, which no key goes through."""
    assert chains(bound(kept)) == {
        ("stage",),
        ("stage", "inner"),
        ("inner",),
        ("lib",),
        ("lib", "deep"),
    }


def test_a_driven_analysis_drives_through_its_own_parent(kept: Path) -> None:
    """§16 *The universe being built*: in `stage`'s universes, `parent: {path: ..}` leads back
    to no analysis already on the chain, so the key `parent.decision1` drives the root."""
    stack = bound(kept)
    stage = Identity("stage")
    assert {("inner",), ("parent",)} <= chains(stack, stage)
    assert set(built(driven(stack)[stage], stage)) >= {stage, Identity("stage/inner"), ROOT_ID}


def test_the_analyses_built_in_a_universe_are_known_by_identity(kept: Path) -> None:
    """§16: the driver itself, and each analysis a driven declaration reaches, once however
    many chains reach it (`stage.inner` and `inner`)."""
    stack = bound(kept)
    assert list(built(driven(stack)[ROOT_ID], ROOT_ID)) == [
        ROOT_ID,
        Identity("stage"),
        Identity("stage/inner"),
        Identity("lib"),
        Identity("lib/deep"),
    ]


def test_a_key_that_loops_drives_nothing(broken: Path) -> None:
    """design §4.13 case 10: `stage2.again.d` loops, so it drives neither `stage2` nor `again`."""
    found = chains(bound(broken))
    assert ("stage2",) not in found
    assert ("stage2", "again") not in found


def test_a_stack_driven_as_written_breaks_no_rule_on_selections(kept: Path) -> None:
    """§16: `stage.inner.d` and `inner.d` spell one decision, set under either in different
    universes; u3 changes it under the key it inherits; `stage`'s `parent.decision1` doesn't
    loop."""
    assert found(api.validate(kept)) == []


# --- the rules ---


def test_each_rule_is_broken_where_sixteens_text_says(broken_report: api.ValidationReport) -> None:
    """§16: two own keys spelling one decision, even selecting one option, and a key spelling
    an inherited decision under another key (DUPLICATE_ELEMENT); `stage.again.d` written through
    `again: {path: .}`, `stage.parent.decision1` back to the root, and `self.decision1`
    (LOOPING_KEY); a universe that leaves unset decisions driven by another universe's keys,
    and a driven analysis's own universe that leaves its own `d`, or its driven parent's
    `decision1`, unset (MISSING_DECISION). A key that loops still names its decision, so the
    excluded `stage.d: c` is EXCLUDED_OPTION_SELECTED and `unset`'s neighbours aren't missing."""
    assert found(broken_report) == [
        ("DUPLICATE_ELEMENT", "astra.yaml", "/universes/two_keys/decisions", "inner.d"),
        ("DUPLICATE_ELEMENT", "astra.yaml", "/universes/other_key/decisions", "inner.d"),
        ("EXCLUDED_OPTION_SELECTED", "astra.yaml", "/universes/again/decisions", "stage2.again.d"),
        ("LOOPING_KEY", "astra.yaml", "/universes/again/decisions", "stage2.again.d"),
        ("LOOPING_KEY", "astra.yaml", "/universes/parent/decisions", "stage.parent.decision1"),
        ("LOOPING_KEY", "astra.yaml", "/universes/itself/decisions", "self.decision1"),
        ("MISSING_DECISION", "astra.yaml", "/universes/unset/decisions", None),
        ("MISSING_DECISION", "astra.yaml", "/universes/unset/decisions", None),
        ("MISSING_DECISION", "stage/astra.yaml", "/universes/s2/decisions", None),
        ("MISSING_DECISION", "stage/astra.yaml", "/universes/s3/decisions", None),
    ]


def test_duplicate_element_names_the_other_key(broken_report: api.ValidationReport) -> None:
    """§16 *What a universe sets*: each decision has one key, so the message says which to
    remove, and the other key is a related place."""
    two, inherited = [d for d in broken_report.diagnostics if d.code == "DUPLICATE_ELEMENT"]
    assert "`inner.d` and `stage.inner.d` spell one decision" in two.message
    assert [(r.pointer, r.key) for r in two.related] == [
        ("/universes/two_keys/decisions", "stage.inner.d")
    ]
    assert "inherits as `stage.inner.d`" in inherited.message
    assert [(r.pointer, r.key) for r in inherited.related] == [
        ("/universes/u1/decisions", "stage.inner.d")
    ]


def test_looping_key_says_how_to_key_the_decision(broken_report: api.ValidationReport) -> None:
    """§16 *Driving*: `stage.d` is never written `stage.again.d`, and the root's own decisions
    are keyed by their ids alone."""
    messages = [d.message for d in broken_report.diagnostics if d.code == "LOOPING_KEY"]
    assert "leads back to `stage2`, already on its chain" in messages[0]
    assert "key the decision as `stage2.d`" in messages[0]
    for message in messages[1:]:
        assert "leads back to this analysis" in message
        assert "key the decision as `decision1`" in message


def test_missing_decision_names_each_decision_unset(broken_report: api.ValidationReport) -> None:
    """§16: whichever universe has the key that drives `stage` and `inner`, `unset` sets their
    decisions."""
    messages = [
        d.message
        for d in broken_report.diagnostics
        if d.code == "MISSING_DECISION" and d.location.file == "astra.yaml"
    ]
    assert [message.split("`")[3] for message in messages] == ["stage.d", "stage.inner.d"]
    assert "this analysis's universes drive `stage`" in messages[0]
    stage = [d.message for d in broken_report.diagnostics if d.location.file == "stage/astra.yaml"]
    assert [message.split("`")[3] for message in stage] == ["d", "parent.decision1"]


def test_nothing_through_an_undetermined_analysis_or_a_name_that_names_nothing(
    broken_report: api.ValidationReport,
) -> None:
    """design §4.13 cases 4, 5 and 10: `bad.parent.decision1` is judged up to `bad`, whose file is
    invalid, and `stage.nothere.parent.decision1` up to `nothere`, which `stage` doesn't
    declare: neither loops; no decision of `bad` is missing; the second names nothing."""
    reported = {
        (d.code, d.location.key)
        for d in broken_report.diagnostics
        if d.location.pointer.startswith(("/universes/through_", "/universes/bad"))
        or d.location.file == "bad/astra.yaml"
    }
    assert reported == {
        ("UNRESOLVED_ADDRESS", "stage.nothere.parent.decision1"),
        ("UNKNOWN_FIELD", "name"),
    }


# --- §16 *Pins and imported universes* ---

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
universes:
  u1:
    decisions: {decision1: a}
  v1:
    decisions: {decision1: b}
  parent_u1: {analysis: parent, universe: u1}
"""
"""§15's `subanalysis`, with universes `u1` and `v1` of its own and an import of its parent's."""

PINNING = """\
spec_version: "0.1.0"
analyses:
  subanalysis: {path: subanalysis}
  again: {path: subanalysis}
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
  output5:
    type: table
    format: csv
    inputs:
      - subanalysis.output1#u1               # the root's u1
      - subanalysis.output1#subanalysis_u1   # subanalysis's own u1, imported
      - subanalysis.output1#v1               # subanalysis's own v1
      - subanalysis.output1#subanalysis_v1   # §12's import of subanalysis's v1
      - output1#u2
      - input1#u1
    recipe:
      command: python make.py '{output}'
  output6:
    type: table
    format: csv
    inputs:
      - subanalysis.output1#v9
      - output1#v1
      - input1#v1
      - subanalysis.output1#parent_u1
      - nothere.output1#v9
      - output1#nothing_v9
    recipe:
      command: python make.py '{output}'
universes:
  u1:                                        # the root's u1 drives subanalysis
    decisions: {decision1: a, subanalysis.decision1: a}
  u2:
    decisions: {decision1: b, subanalysis.decision1: b}
  subanalysis_u1:                            # an import of subanalysis's u1
    analysis: subanalysis
    universe: u1
  subanalysis_v1:                  # an import of subanalysis's own universe v1
    analysis: subanalysis
    universe: v1
  again_u1: {analysis: again, universe: u1}
  nothing_v9: {analysis: subanalysis, universe: v9}
findings:
  insight1:
    claim: The two universes differ.
    evidence: [{artifact: "output1#u9"}, {artifact: "subanalysis.output1#v1"}]
"""
"""§16's `output5`, and in `output6` a pin for each way to name no universe."""


@pytest.fixture(scope="module")
def pinning(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {
        "astra.yaml": PINNING,
        "data/input1.csv": "1\n",
        "subanalysis/astra.yaml": SUBANALYSIS,
        "subanalysis/data/input1.csv": "2\n",
    }
    return repository(tmp_path_factory.mktemp("pinning"), files)


def test_a_pin_names_the_files_entry_or_the_elements_analysiss_universe(pinning: Path) -> None:
    """§16 *Pins and imported universes*: `#u1` names the root's own `u1`, `#subanalysis_u1`
    the universe the import names, and `#v1`, since the root has no `v1`, `subanalysis`'s, as
    §12's import `subanalysis_v1` does; a pin on an input names a universe too."""
    stack = bound(pinning)
    named = {
        r.pointer: pinned
        for r, pinned in pins(stack, imports(stack)).items()
        if r.file == ROOT_ID and r.pointer[:2] == ("outputs", "output5")
    }
    subanalysis = Identity("subanalysis")
    assert named == {
        ("outputs", "output5", "inputs", 0): Element(ROOT_ID, "universe", "u1"),
        ("outputs", "output5", "inputs", 1): Element(subanalysis, "universe", "u1"),
        ("outputs", "output5", "inputs", 2): Element(subanalysis, "universe", "v1"),
        ("outputs", "output5", "inputs", 3): Element(subanalysis, "universe", "v1"),
        ("outputs", "output5", "inputs", 4): Element(ROOT_ID, "universe", "u2"),
        ("outputs", "output5", "inputs", 5): Element(ROOT_ID, "universe", "u1"),
    }


def test_imports_of_one_universe_name_that_one_universe(pinning: Path) -> None:
    """§16: an import resolves in its file by identity, under any id and through any
    declaration; one in a driven analysis's file can name its parent's universe."""
    found = imports(bound(pinning))
    subanalysis_u1 = Element(Identity("subanalysis"), "universe", "u1")
    assert found[ROOT_ID, "subanalysis_u1"] == found[ROOT_ID, "again_u1"] == subanalysis_u1
    assert found[ROOT_ID, "subanalysis_v1"] == Element(Identity("subanalysis"), "universe", "v1")
    assert found[ROOT_ID, "nothing_v9"] is None
    assert found[Identity("subanalysis"), "parent_u1"] == Element(ROOT_ID, "universe", "u1")


def test_a_pin_that_names_no_universe_breaks_unknown_pin_universe(pinning: Path) -> None:
    """§16: neither the file nor the element's analysis has the universe, as for an element of
    the file's own analysis; an import in the other analysis's file isn't one of its universes;
    and evidence pins as `Output.inputs` does (§14). A reference that names nothing isn't
    checked (design §4.13 case 5), nor a pin naming the file's entry, an import that names
    nothing."""
    report = api.validate(pinning)
    pinned = [
        (d.location.pointer, d.level)
        for d in report.diagnostics
        if d.code == "UNKNOWN_PIN_UNIVERSE"
    ]
    assert pinned == [
        ("/outputs/output6/inputs/0", "error"),
        ("/outputs/output6/inputs/1", "error"),
        ("/outputs/output6/inputs/2", "error"),
        ("/outputs/output6/inputs/3", "error"),
        ("/findings/insight1/evidence/0/artifact", "error"),
    ]
    messages = [d.message for d in report.diagnostics if d.code == "UNKNOWN_PIN_UNIVERSE"]
    assert "nor has `subanalysis` a universe `v9`" in messages[0]
    assert "is an import in `subanalysis`'s file" in messages[3]


def test_examples_iris_pipeline_drives_as_written(tmp_path: Path) -> None:
    """astra-spec's `examples/iris_pipeline`: the root's universes drive both stages, whose
    `..` and sibling declarations lead nowhere they must set; `mlp_svm` inherits the rest."""
    shutil.copytree(SPEC / "examples" / "iris_pipeline", tmp_path / "pipeline")
    top = repository(tmp_path / "pipeline", {})
    assert found(api.validate(top)) == []
    assert chains(bound(top)) == {("feature_extraction",), ("classification",)}
