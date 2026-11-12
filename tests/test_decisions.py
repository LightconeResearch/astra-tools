"""Decisions and options: `UNKNOWN_OPTION`, in option references, universes' own selections
and the keys of a switch's `cases`; on a key that loops too, but not under a name that names
nothing or through an undetermined analysis."""

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

BROKEN = """\
spec_version: "0.1.0"
analyses:
  sub: {path: sub}
  self: {path: .}
  bad: {path: bad}
decisions:
  decision1:
    options:
      a:
        requires: [decision2.z]
        incompatible_with: [sub.decision1.z, decision9.z, bad.decision1.z]
      b: {}
  decision2:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  switch1:
    switch: sub.decision1
    cases: {a: output1, z: output1}
  switch9:
    switch: decision9
    cases: {z: output1}
  switch_bad:
    switch: bad.decision1
    cases: {z: output1}
universes:
  u1:
    decisions: {decision1: c, sub.decision1: z, decision9: c, self.decision1: c, bad.decision1: z}
  u2:
    derived_from: u1
    decisions: {decision2: z}
"""
"""Each option named that isn't one of its decision's, and some under an address that names
nothing (`decision9`) or goes through an undetermined analysis (`bad`)."""


@pytest.fixture(scope="module")
def broken(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    files = {"astra.yaml": BROKEN, "sub/astra.yaml": SUB, "bad/astra.yaml": SUB + "name: x\n"}
    return api.validate(repository(tmp_path_factory.mktemp("broken"), files))


def unknown(report: api.ValidationReport) -> list[str]:
    return [d.location.pointer for d in report.diagnostics if d.code == "UNKNOWN_OPTION"]


def test_an_option_its_decision_lacks_breaks_unknown_option(broken: api.ValidationReport) -> None:
    """In a constraint, through a declaration too; and in a universe's own selection, derived
    or not, reported at the option selected. The key `self.decision1` loops, and still names its
    decision."""
    assert unknown(broken) == [
        "/decisions/decision1/options/a/requires/0",
        "/decisions/decision1/options/a/incompatible_with/0",
        "/outputs/switch1/cases",
        "/universes/u1/decisions/decision1",
        "/universes/u1/decisions/sub.decision1",
        "/universes/u1/decisions/self.decision1",
        "/universes/u2/decisions/decision2",
    ]
    found = {d.location.pointer: d for d in broken.diagnostics if d.code == "UNKNOWN_OPTION"}
    selection = found["/universes/u1/decisions/sub.decision1"]
    assert (selection.level, selection.location.line, selection.location.column) == (
        "error",
        32,
        46,
    )
    assert "`a`, `b`" in selection.message


def test_a_key_of_cases_its_switchs_decision_lacks_breaks_it(broken: api.ValidationReport) -> None:
    """Elements *switch*: the keys of `cases` are options of the decision its `switch` names,
    through a declaration too; reported at the key, which is what is misspelt."""
    (case,) = [
        d
        for d in broken.diagnostics
        if d.code == "UNKNOWN_OPTION" and d.location.pointer == "/outputs/switch1/cases"
    ]
    assert (case.location.key, case.location.line, case.location.column) == ("z", 23, 25)
    assert "`switch1` switches on `sub.decision1`, which has no option `z`" in case.message
    assert "`a`, `b`" in case.message


def test_nothing_under_an_address_that_names_nothing_is_checked(
    broken: api.ValidationReport,
) -> None:
    """`decision9` names nothing, so `decision9: c` isn't checked for its option, nor is a key of
    the cases of a switch on it; nor is `bad.decision1.z`, through an undetermined analysis, nor
    a key under `switch: bad.decision1`."""
    assert not any("decision9" in pointer or "bad" in pointer for pointer in unknown(broken))
    assert "/decisions/decision1/options/a/incompatible_with/1" not in unknown(broken)
    assert "/outputs/switch9/cases" not in unknown(broken)


KEPT = """\
spec_version: "0.1.0"
analyses:
  sub: {path: sub}
decisions:
  decision1:
    rationale: Both are reasonable, and they may give different results.
    options:
      a: {}
      b:
        requires: [decision2.b]
        incompatible_with: [sub.decision1.a]
  decision2:
    options:
      a: {}
      b: {}
      c:
        excluded: It needs data this analysis doesn't have.
outputs:
  output4:
    type: figure
    format: png
    recipe:
      command: python src/output4.py '{output}'
  switch1:
    switch: decision2
    cases: {a: output4, c: output4}
  switch2:
    switch: sub.decision1
    cases: {b: switch1}
universes:
  u1:
    decisions: {decision1: a, decision2: a, sub.decision1: a}
  u2:
    derived_from: u1
    decisions: {decision1: b, decision2: b}
"""
"""Decisions with constraints and an excluded option, and universes, one derived from another."""


def test_options_of_their_decisions_keep_it(tmp_path: Path) -> None:
    """An excluded option is still one of its decision's options, and may key a case
    (Elements *switch*); a switch's decision may be another analysis's."""
    files = {"astra.yaml": KEPT, "sub/astra.yaml": SUB}
    assert unknown(api.validate(repository(tmp_path, files))) == []
