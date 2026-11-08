"""§12 Universes: effective selections, the activity of §9 in them, and `UNKNOWN_DERIVED_FROM`,
`DERIVED_FROM_CYCLE`, `MISSING_REQUIRED_OPTION`, `INCOMPATIBLE_OPTIONS`,
`EXCLUDED_OPTION_SELECTED` and `INACTIVE_DECISION`, with design §4.13 cases 6 and 7 and design §5's
O16.

The stacks are §12's: §8's decisions, §9's `decision3`, and §15's `subanalysis`, which the root's
universes drive. The keeping one has §12's `u1`, `u2` and `u3`; the breaking one, a universe for
each way to break a rule. astra-spec's `examples/iris` gives `incompatible_with`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from astra import api, rules
from astra.sources.git import Repository
from astra.sources.reader import WorktreeReader
from astra.stack import Element, Identity, bind
from astra.universes import Selection, driven, selections, written
from tests.conftest import MINIMAL, SPEC, repository

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
"""§15's `subanalysis`, with a universe `v1` of its own."""

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
  decision3:
    when: [decision1.b]
    options:
      a: {}
      b: {}
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
  output4:
    type: figure
    format: png
    when: [decision1.b]
    recipe:
      command: python src/output4.py '{output}'
universes:
  u1:
    decisions: {decision1: a, decision2: a, subanalysis.decision1: a}
  u2:
    derived_from: u1
    decisions: {decision1: b, decision2: b, decision3: a}
"""
"""§8's decisions, §9's `decision3` and `output4`, and §12's `u1` and `u2`."""

KEPT = (
    ROOT
    + """\
  u3:
    derived_from: u2
    decisions: {decision1: a}   # the inherited decision3 is dropped
"""
)

BROKEN = (
    ROOT
    + """\
  inactive:
    derived_from: u2
    decisions: {decision1: a, decision3: a}
  requires:
    decisions: {decision1: b, decision2: a, decision3: a, subanalysis.decision1: a}
  inherits:
    derived_from: requires
    decisions: {decision3: b}
  excluded:
    decisions: {decision1: a, decision2: c, subanalysis.decision1: a}
  unknown:
    derived_from: u9
    decisions: {decision1: a, decision3: a, decision9: a}
  from_import:
    derived_from: subanalysis_v1
  subanalysis_v1: {analysis: subanalysis, universe: v1}
  loop1: {derived_from: loop2}
  loop2: {derived_from: loop1}
  itself: {derived_from: itself}
  reaches:
    derived_from: loop1
    decisions: {decision3: a}
  unset:
    decisions: {decision2: b, decision3: a, subanalysis.decision1: a}
  unknown_option:
    decisions: {decision1: z, decision2: b, decision3: a, subanalysis.decision1: a}
  keeps:
    derived_from: u2
    decisions: {decision1: z}
  both_unset:
    decisions: {decision2: b, subanalysis.decision1: a}
"""
)

FILES = {
    "subanalysis/astra.yaml": SUBANALYSIS,
    "subanalysis/data/input1.csv": "1,2\n",
    "subanalysis/src/output1.py": "",
    "src/output1.py": "",
    "src/output4.py": "",
}

CHECKED = rules.universes.CODES | rules.driving.CODES
"""The codes of §12's and §16's rules on selections."""

ROOT_ID = Identity("")


def universe(id_: str) -> Element:
    return Element(ROOT_ID, "universe", id_)


def decision(id_: str, analysis: str = "") -> Element:
    return Element(Identity(analysis), "decision", id_)


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
    return selections(stack, written(stack))


@pytest.fixture(scope="module")
def kept(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("kept"), {"astra.yaml": KEPT, **FILES})


@pytest.fixture(scope="module")
def broken(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("broken"), {"astra.yaml": BROKEN, **FILES})


@pytest.fixture(scope="module")
def broken_report(broken: Path) -> api.ValidationReport:
    return api.validate(broken)


# --- §12 The effective selection ---


def test_the_effective_selections_are_twelves_table(kept: Path) -> None:
    """§12: once `derived_from` is resolved, u2 inherits `subanalysis.decision1`, and u3
    switches `decision3` off, so the `decision3: a` it inherits from u2 is dropped (step 3)."""
    found = effective(kept)
    assert selected(found[universe("u1")]) == {
        "decision1": "a",
        "decision2": "a",
        "subanalysis.decision1": "a",
    }
    assert selected(found[universe("u2")]) == {
        "decision1": "b",
        "decision2": "b",
        "decision3": "a",
        "subanalysis.decision1": "a",
    }
    assert selected(found[universe("u3")]) == {
        "decision1": "a",
        "decision2": "b",
        "subanalysis.decision1": "a",
    }


def test_a_driven_analysiss_own_universes_have_effective_selections(kept: Path) -> None:
    """§16 *What a validator checks*: every universe of every analysis of the stack."""
    found = effective(kept)
    assert selected(found[Element(Identity("subanalysis"), "universe", "v1")]) == {"decision1": "a"}


def test_an_element_is_active_where_its_when_holds(kept: Path) -> None:
    """§9: `decision3` and `output4` are active only where `decision1.b` is selected; an
    element without `when` is always active."""
    found = effective(kept)
    output4 = Element(ROOT_ID, "output", "output4")
    for id_, active in (("u1", False), ("u2", True), ("u3", False)):
        selection = found[universe(id_)]
        assert selection is not None
        assert (selection.active(decision("decision3")), selection.active(output4)) == (
            active,
            active,
        )
        assert selection.active(decision("decision1")) is True


def test_twelves_universes_break_no_rule_on_selections(kept: Path) -> None:
    """§12: u2 selects `decision3` itself, where `decision1: b` makes it active, and
    `decision2: b`, which `decision1.b` requires; u3 sets nothing inactive itself."""
    assert found(api.validate(kept)) == []


# --- §12's rules ---


def test_each_rule_is_broken_where_twelves_text_says(broken_report: api.ValidationReport) -> None:
    """§12: a universe that sets an inactive decision itself (u3 couldn't select `decision3`);
    a selection whose `requires` isn't selected, set or inherited; an excluded option (§8); a
    `derived_from` naming no universe or an import; and each universe on a loop."""
    assert [f for f in found(broken_report) if f[0] != "MISSING_DECISION"] == [
        ("INACTIVE_DECISION", "/universes/inactive/decisions", "decision3"),
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
    """Design §3: `inherits` inherits `decision1: b` from `requires`; the places where that key
    and its `requires` are written are related."""
    (diagnostic,) = [
        d for d in broken_report.diagnostics if d.location.pointer.startswith("/universes/inherits")
    ]
    assert (diagnostic.location.line, diagnostic.location.column) == (50, 19)
    assert [(r.pointer, r.key) for r in diagnostic.related] == [
        ("/universes/requires/decisions", "decision1"),
        ("/decisions/decision1/options/b/requires/0", None),
    ]
    assert "inherits `decision1: b` from `requires`" in diagnostic.message


def test_a_universe_with_no_effective_selection_has_its_own_decisions_checked(
    broken: Path, broken_report: api.ValidationReport
) -> None:
    """design §4.13 case 7: `unknown`, `from_import`, the loop and `reaches`, which only reaches it,
    have none, so `unknown`'s `decision3` isn't INACTIVE_DECISION nor its `decision2`
    MISSING_DECISION; UNRESOLVED_ADDRESS is still checked on its own `decisions`."""
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


def test_an_undetermined_activity_checks_no_rule_on_it(
    broken: Path, broken_report: api.ValidationReport
) -> None:
    """design §4.13 case 6: in `unset` `decision1` is unset (MISSING_DECISION), and in
    `unknown_option` set to an option that names nothing, so `decision3`'s `when` is
    undetermined: setting it isn't INACTIVE_DECISION, and in `both_unset`, which leaves it unset
    too, it isn't MISSING_DECISION; nor is `output4` active or inactive."""
    found = effective(broken)
    for id_ in ("unset", "unknown_option", "both_unset"):
        selection = found[universe(id_)]
        assert selection is not None
        assert selection.active(decision("decision3")) is None
        assert selection.active(Element(ROOT_ID, "output", "output4")) is None
    reported = [
        (d.code, d.location.pointer)
        for d in broken_report.diagnostics
        if d.code in CHECKED and d.location.pointer.startswith("/universes/unset")
    ]
    assert reported == [("MISSING_DECISION", "/universes/unset/decisions")]
    assert "`decision1`" in next(
        d.message for d in broken_report.diagnostics if d.code == "MISSING_DECISION"
    )
    assert not any(
        d.code in CHECKED and d.location.pointer.startswith("/universes/unknown_option")
        for d in broken_report.diagnostics
    )
    (missing,) = [
        d.message
        for d in broken_report.diagnostics
        if d.code in CHECKED and d.location.pointer.startswith("/universes/both_unset")
    ]
    assert "selects nothing for `decision1`" in missing


INACTIVE_UNSET = (
    MINIMAL
    + """\
decisions:
  decision1:
    options: {a: {}, b: {}}
  decision3:
    when: [decision1.b]
    options: {a: {}, b: {}}
  decision4:
    when: [~decision3.a]
    options: {x: {}, y: {}}
universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: a, decision4: x}
"""
)
"""§9's `decision3`, and a `decision4` that is active where `decision3.a` isn't selected."""


def test_a_condition_on_an_inactive_decision_left_unset_is_determined(tmp_path: Path) -> None:
    """design §5, O16: where `decision1: a` is selected, `decision3` is inactive and has no
    option selected, so `~decision3.a` holds: `decision4` is active, and `u1`, which leaves it
    unset, breaks MISSING_DECISION (§16)."""
    report = api.validate(repository(tmp_path, {"astra.yaml": INACTIVE_UNSET}))
    assert [(d.code, d.location.pointer) for d in report.diagnostics] == [
        ("MISSING_DECISION", "/universes/u1/decisions")
    ]
    assert "selects nothing for `decision4`" in report.diagnostics[0].message


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
    """design §4.13 case 7: `unknown` has no effective selection, but UNKNOWN_OPTION
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
    assert {tuple(d.id for d in chain) for chain in driven(stack)[ROOT_ID]} == {
        ("subanalysis",),
        ("again",),
    }


def test_step_3_doesnt_drop_a_decision_whose_activity_is_undetermined(broken: Path) -> None:
    """design §4.13 case 6: `keeps` sets `decision1` to an option that names nothing, so the
    `decision3: a` it inherits from u2 stays."""
    assert selected(effective(broken)[universe("keeps")]) == {
        "decision1": "z",
        "decision2": "b",
        "decision3": "a",
        "subanalysis.decision1": "a",
    }


# --- §8's constraints, in astra-spec's examples/iris ---

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
    """§8: `minmax` is incompatible with `model.svm`, and `svm` requires `scaling.standard`,
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
