"""§8 Decisions and options: `UNKNOWN_OPTION`, in conditions, option references and universes'
own selections, with Annex D cases 4, 5 and 10."""

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
    when: [decision1.c]
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    when: ["~decision1.c", decision9.c]
    recipe:
      command: python make.py '{output}'
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
    """§8: in a constraint, through a declaration too; in a condition, `~` or not; and in a
    universe's own selection, derived or not, reported at the option selected. Annex D case
    10: the key `self.decision1` loops, and still names its decision."""
    assert unknown(broken) == [
        "/decisions/decision1/options/a/requires/0",
        "/decisions/decision1/options/a/incompatible_with/0",
        "/decisions/decision2/when/0",
        "/outputs/output1/when/0",
        "/universes/u1/decisions/decision1",
        "/universes/u1/decisions/sub.decision1",
        "/universes/u1/decisions/self.decision1",
        "/universes/u2/decisions/decision2",
    ]
    found = {d.location.pointer: d for d in broken.diagnostics if d.code == "UNKNOWN_OPTION"}
    selection = found["/universes/u1/decisions/sub.decision1"]
    assert (selection.level, selection.location.line, selection.location.column) == (
        "error",
        25,
        46,
    )
    assert "`a`, `b`" in selection.message


def test_nothing_under_an_address_that_names_nothing_is_checked(
    broken: api.ValidationReport,
) -> None:
    """Annex D case 5: `decision9` names nothing, so `decision9.c` and `decision9: c` aren't
    checked for their option; case 4: nor is `bad.decision1.z`, through an undetermined
    analysis."""
    assert not any("decision9" in pointer or "bad" in pointer for pointer in unknown(broken))
    assert "/decisions/decision1/options/a/incompatible_with/1" not in unknown(broken)


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
  decision3:
    when: [decision1.b]
    options: {a: {}, b: {}}
outputs:
  output4:
    type: figure
    format: png
    when: ["~decision1.a", "~decision2.c"]
    recipe:
      command: python src/output4.py '{output}'
universes:
  u1:
    decisions: {decision1: a, decision2: a, sub.decision1: a}
  u2:
    derived_from: u1
    decisions: {decision1: b, decision2: b, decision3: a}
"""
"""§8's fragment, §9's conditions and §12's universes, with `subanalysis` as `sub`."""


def test_options_of_their_decisions_keep_it(tmp_path: Path) -> None:
    """§8, §9, §12: an excluded option is still one of its decision's options."""
    files = {"astra.yaml": KEPT, "sub/astra.yaml": SUB}
    assert unknown(api.validate(repository(tmp_path, files))) == []
