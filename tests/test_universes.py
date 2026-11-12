"""Universes: effective selections, and `UNKNOWN_DERIVED_FROM`, `DERIVED_FROM_CYCLE`,
`MISSING_REQUIRED_OPTION`, `INCOMPATIBLE_OPTIONS` and `EXCLUDED_OPTION_SELECTED`, and what is
still checked for a universe with no effective selection.

The stacks share the root's two decisions and `subanalysis`, which the root's universes drive.
The keeping one has `u1`, `u2` and `u3`; the breaking one, a universe for each way to break a
rule. astra-spec's `examples/iris` gives `incompatible_with`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from astra import api, rules
from astra.diagnostics import Catalogue
from astra.rules.context import Context
from astra.sources.git import Repository
from astra.sources.reader import WorktreeReader
from astra.stack import Element, Identity, bind
from astra.universes import Selection, selections
from tests.conftest import SPEC, repository

SUBANALYSIS = """\
spec_version: "0.1.0"
inputs:
  input1:
    path: data/input1.csv
decisions:
  decision1:
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
      command: python src/output1.py '{inputs.input1}' '{decisions.decision1}' '{output}'
universes:
  v1:
    decisions: {decision1: a}
"""
"""The declared analysis `subanalysis`, with a universe `v1` of its own."""

ROOT = """\
spec_version: "0.1.0"
analyses:
  subanalysis: {path: subanalysis}
decisions:
  decision1:
    rationale: Both are reasonable, and they may give different results.
    options:
      a: {}
      b:
        requires: [decision2.b]
  decision2:
    options:
      a: {}
      b: {}
      c:
        excluded: It needs data this analysis doesn't have.
outputs:
  output1:
    type: metric
    format: json
    inputs: [subanalysis.output1]
    decisions: [decision1, decision2]
    recipe:
      command: >-
        python src/output1.py '{inputs.subanalysis.output1}' '{decisions.decision1}'
        '{decisions.decision2}' '{output}'
universes:
  u1:
    decisions: {decision1: a, decision2: a, subanalysis.decision1: a}
  u2:
    derived_from: u1
    decisions: {decision1: b, decision2: b}
"""
"""Two decisions, with a `requires` and an excluded option; `u1`, and `u2` derived from it."""

KEPT = (
    ROOT
    + """\
  u3:
    derived_from: u2
    decisions: {decision1: a}   # replaces the decision1 it inherits
"""
)

BROKEN = (
    ROOT
    + """\
  requires:
    decisions: {decision1: b, decision2: a, subanalysis.decision1: a}
  inherits:
    derived_from: requires
    decisions: {subanalysis.decision1: b}
  excluded:
    decisions: {decision1: a, decision2: c, subanalysis.decision1: a}
  unknown:
    derived_from: u9
    decisions: {decision1: a, decision9: a}
  from_import:
    derived_from: subanalysis_v1
  subanalysis_v1: {analysis: subanalysis, universe: v1}
  loop1: {derived_from: loop2}
  loop2: {derived_from: loop1}
  itself: {derived_from: itself}
  reaches:
    derived_from: loop1
    decisions: {decision1: a}
"""
)

FILES = {
    "subanalysis/astra.yaml": SUBANALYSIS,
    "subanalysis/data/input1.csv": "1,2\n",
    "subanalysis/src/output1.py": "",
    "src/output1.py": "",
}

CHECKED = rules.universes.CODES | rules.driving.CODES
"""The codes of the rules on universes and on driving."""

ROOT_ID = Identity("")


def universe(id_: str) -> Element:
    return Element(ROOT_ID, "universe", id_)


def selected(selection: Selection | None) -> dict[str, str | None]:
    assert selection is not None
    return {str(entry.key): entry.option for entry in selection.entries}


def found(report: api.ValidationReport) -> list[tuple[str, str, str | None]]:
    return [
        (d.code, d.location.pointer, d.location.key)
        for d in report.diagnostics
        if d.code in CHECKED
    ]


def effective(top: Path) -> Mapping[Element, Selection | None]:
    """Every universe's effective selection, in the stack whose root is `top`."""
    stack = bind(WorktreeReader(top, Repository(top)), "").stack
    assert stack is not None
    return selections(stack)


@pytest.fixture(scope="module")
def kept(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("kept"), {"astra.yaml": KEPT, **FILES})


@pytest.fixture(scope="module")
def broken(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("broken"), {"astra.yaml": BROKEN, **FILES})


@pytest.fixture(scope="module")
def broken_report(broken: Path) -> api.ValidationReport:
    return api.validate(broken)


# --- The effective selection ---


def test_the_effective_selections_resolve_derived_from(kept: Path) -> None:
    """Once `derived_from` is resolved, u2 inherits `subanalysis.decision1`, and u3
    replaces `decision1` and inherits the rest."""
    found = effective(kept)
    assert selected(found[universe("u1")]) == {
        "decision1": "a",
        "decision2": "a",
        "subanalysis.decision1": "a",
    }
    assert selected(found[universe("u2")]) == {
        "decision1": "b",
        "decision2": "b",
        "subanalysis.decision1": "a",
    }
    assert selected(found[universe("u3")]) == {
        "decision1": "a",
        "decision2": "b",
        "subanalysis.decision1": "a",
    }


def test_a_driven_analysiss_own_universes_have_effective_selections(kept: Path) -> None:
    """A validator checks every universe of every analysis of the stack."""
    found = effective(kept)
    assert selected(found[Element(Identity("subanalysis"), "universe", "v1")]) == {"decision1": "a"}


def test_the_kept_universes_break_no_rule_on_selections(kept: Path) -> None:
    """u2 selects `decision2: b`, which `decision1.b` requires."""
    assert found(api.validate(kept)) == []


# --- The rules on universes ---


def test_each_rule_on_selections_is_broken(broken_report: api.ValidationReport) -> None:
    """A selection whose `requires` isn't selected, set or inherited; an excluded option; a
    `derived_from` naming no universe or an import; and each universe on a loop."""
    assert [f for f in found(broken_report) if f[0] != "MISSING_DECISION"] == [
        ("MISSING_REQUIRED_OPTION", "/universes/requires/decisions", "decision1"),
        ("MISSING_REQUIRED_OPTION", "/universes/inherits/derived_from", None),
        ("EXCLUDED_OPTION_SELECTED", "/universes/excluded/decisions", "decision2"),
        ("UNKNOWN_DERIVED_FROM", "/universes/unknown/derived_from", None),
        ("UNKNOWN_DERIVED_FROM", "/universes/from_import/derived_from", None),
        ("DERIVED_FROM_CYCLE", "/universes/loop1/derived_from", None),
        ("DERIVED_FROM_CYCLE", "/universes/loop2/derived_from", None),
        ("DERIVED_FROM_CYCLE", "/universes/itself/derived_from", None),
    ]
    assert all(d.level == "error" for d in broken_report.diagnostics if d.code in CHECKED)


def test_an_inherited_selection_is_reported_at_derived_from(
    broken_report: api.ValidationReport,
) -> None:
    """`inherits` inherits `decision1: b` from `requires`; the places where that key
    and its `requires` are written are related."""
    (diagnostic,) = [
        d for d in broken_report.diagnostics if d.location.pointer.startswith("/universes/inherits")
    ]
    assert (diagnostic.location.line, diagnostic.location.column) == (36, 19)
    assert [(r.pointer, r.key) for r in diagnostic.related] == [
        ("/universes/requires/decisions", "decision1"),
        ("/decisions/decision1/options/b/requires/0", None),
    ]
    assert "inherits `decision1: b` from `requires`" in diagnostic.message


def test_a_universe_with_no_effective_selection_has_its_own_decisions_checked(
    broken: Path, broken_report: api.ValidationReport
) -> None:
    """`unknown`, `from_import`, the loop and `reaches`, which only reaches it,
    have none, so `unknown`'s `decision2` isn't MISSING_DECISION; UNRESOLVED_ADDRESS is still
    checked on its own `decisions`."""
    found = effective(broken)
    for id_ in ("unknown", "from_import", "loop1", "loop2", "itself", "reaches"):
        assert found[universe(id_)] is None
    reported = {
        (d.code, d.location.key)
        for d in broken_report.diagnostics
        if d.location.pointer.startswith(("/universes/unknown/", "/universes/reaches/"))
    }
    assert reported == {
        ("UNKNOWN_DERIVED_FROM", None),
        ("UNRESOLVED_ADDRESS", "decision9"),
    }


NO_SELECTION = """\
spec_version: "0.1.0"
analyses:
  subanalysis: {path: subanalysis}
  again: {path: subanalysis}
  self: {path: .}
decisions:
  decision1:
    options: {a: {}, b: {}}
  decision2:
    options: {a: {}, b: {}}
outputs:
  result:
    type: metric
    format: json
    decisions: [decision1, decision2, subanalysis.decision1]
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a, decision2: a}
  unknown:
    derived_from: u9
    decisions: {subanalysis.decision1: a, again.decision1: a, self.decision1: a, decision2: z}
"""
"""A universe with no effective selection whose own keys break each rule still checked on them,
and are the only ones through `subanalysis` and `again`, two declarations of one folder."""


def test_a_universe_with_no_effective_selection_checks_and_drives_by_its_own_keys(
    tmp_path: Path,
) -> None:
    """`unknown` has no effective selection, but UNKNOWN_OPTION
    (`decision2: z`), DUPLICATE_ELEMENT (`again.decision1` spells `subanalysis.decision1`) and
    LOOPING_KEY (`self.decision1`) are still checked on its own `decisions`; and driving counts
    them, so the root's universes drive `subanalysis` and `again`, and `u1`, which leaves
    `subanalysis`'s `decision1` unset, breaks MISSING_DECISION."""
    top = repository(tmp_path, {**FILES, "astra.yaml": NO_SELECTION})
    report = api.validate(top)
    assert sorted((d.code, d.location.pointer, d.location.key) for d in report.diagnostics) == [
        ("DUPLICATE_ELEMENT", "/universes/unknown/decisions", "again.decision1"),
        ("LOOPING_KEY", "/universes/unknown/decisions", "self.decision1"),
        ("MISSING_DECISION", "/universes/u1/decisions", None),
        ("UNKNOWN_DERIVED_FROM", "/universes/unknown/derived_from", None),
        ("UNKNOWN_OPTION", "/universes/unknown/decisions/decision2", None),
    ]
    assert "selects nothing for `subanalysis.decision1`" in next(
        d.message for d in report.diagnostics if d.code == "MISSING_DECISION"
    )
    stack = bind(WorktreeReader(top, Repository(top)), "").stack
    assert stack is not None
    driven = Context(stack, Catalogue.load()).driven
    assert {tuple(d.id for d in chain) for chain in driven[ROOT_ID]} == {
        ("subanalysis",),
        ("again",),
    }


# --- Constraints, in astra-spec's examples/iris ---

IRIS_UNIVERSES = """\
  mixed:
    decisions:
      scaling: minmax
      model: svm
      test_size: small
      random_seed: seed_42
  svm_minmax:
    derived_from: svm_focused
    decisions:
      scaling: minmax
"""


def test_the_iris_examples_constraints(tmp_path: Path) -> None:
    """`minmax` is incompatible with `model.svm`, and `svm` requires `scaling.standard`,
    which `svm_focused` inherits from `baseline` and keeps; `svm_minmax` sets `minmax` itself
    and inherits `svm`."""
    text = (SPEC / "examples" / "iris" / "astra.yaml").read_text(encoding="utf-8")
    report = api.validate(repository(tmp_path, {"astra.yaml": text + IRIS_UNIVERSES}))
    assert found(report) == [
        ("INCOMPATIBLE_OPTIONS", "/universes/mixed/decisions", "scaling"),
        ("MISSING_REQUIRED_OPTION", "/universes/mixed/decisions", "model"),
        ("MISSING_REQUIRED_OPTION", "/universes/svm_minmax/derived_from", None),
        ("INCOMPATIBLE_OPTIONS", "/universes/svm_minmax/decisions", "scaling"),
    ]
    incompatible = report.diagnostics[0]
    assert [r.pointer for r in incompatible.related] == [
        "/decisions/scaling/options/minmax/incompatible_with/0"
    ]
