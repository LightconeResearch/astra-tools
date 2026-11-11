"""§6 Names: `UNRESOLVED_ADDRESS`, in every field §6's table lists, with design §4.13 cases 4 and 5.

The breaking cases share one stack, whose every address names nothing; the keeping ones another,
whose every address resolves, through spellings, `self: {path: .}` and `..` too (§15)."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra import api
from tests.conftest import repository

SUB = """\
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
    inputs: [input1, parent.%s]
    decisions: [decision1]
    recipe:
      command: python make.py '{output}'
universes:
  v1:
    decisions: {decision1: a}
  sub_v1: {analysis: parent, universe: u1}
"""
"""§15's `subanalysis`, with a universe `v1` of its own, an import, and an output reading one
of its parent's through `..`."""

BROKEN = """\
spec_version: "0.1.0"
analyses:
  sub: {path: sub}
  self: {path: .}
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options:
      a:
        requires: [decision9.a]
        incompatible_with: [sub.nothere.decision1.a]
      b: {}
outputs:
  output1:
    type: metric
    format: json
    inputs: [input9, sub.output9, nothere.output1, sub.decision1#v1]
    decisions: [decision9, sub.output1]
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a, decision9: a, sub.decision9: a}
  u2:
    derived_from: u1
    decisions: {decision1: b}
  imp1: {analysis: nothere, universe: v1}
  imp2: {analysis: sub, universe: v9}
  imp3: {analysis: sub, universe: sub_v1}
  imp4: {analysis: self, universe: u1}
findings:
  insight1:
    claim: The input isn't an output.
    evidence: [{artifact: input1}]
"""

KEPT = """\
spec_version: "0.1.0"
analyses:
  sub: {path: sub}
  again: {path: ./sub/}
  self: {path: .}
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options:
      a:
        requires: [again.decision1.a]
        incompatible_with: [self.decision1.b]
      b: {}
outputs:
  output1:
    type: metric
    format: json
    inputs: [input1, sub.output1#v1, again.output1, sub.parent.input1, self.output2]
    decisions: [decision1, sub.decision1, sub.parent.decision1]
    recipe:
      command: python make.py '{output}'
  output2:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a, sub.decision1: a}
  sub_v1: {analysis: sub, universe: v1}
  again_v1: {analysis: again.parent.sub, universe: v1}
findings:
  insight1:
    claim: Both spellings name one output.
    evidence: [{artifact: "sub.output1#v1"}, {artifact: again.output1}, {artifact: self.output2}]
"""


def unresolved(report: api.ValidationReport) -> list[tuple[str, str, str | None]]:
    return [
        (d.location.file, d.location.pointer, d.location.key)
        for d in report.diagnostics
        if d.code == "UNRESOLVED_ADDRESS"
    ]


@pytest.fixture(scope="module")
def broken(tmp_path_factory: pytest.TempPathFactory) -> api.ValidationReport:
    files = {"astra.yaml": BROKEN, "sub/astra.yaml": SUB % "output9"}
    return api.validate(repository(tmp_path_factory.mktemp("broken"), files))


def test_every_field_of_sixs_table_breaks_it(broken: api.ValidationReport) -> None:
    """§6 *Addresses*: an address that doesn't resolve to an element of its field's kind, in
    each field of the table; each written address is reported once, not again in the
    universe that inherits it (§12)."""
    assert unresolved(broken) == [
        ("astra.yaml", "/decisions/decision1/options/a/requires/0", None),
        ("astra.yaml", "/decisions/decision1/options/a/incompatible_with/0", None),
        ("astra.yaml", "/outputs/output1/inputs/0", None),
        ("astra.yaml", "/outputs/output1/inputs/1", None),
        ("astra.yaml", "/outputs/output1/inputs/2", None),
        ("astra.yaml", "/outputs/output1/inputs/3", None),
        ("astra.yaml", "/outputs/output1/decisions/0", None),
        ("astra.yaml", "/outputs/output1/decisions/1", None),
        ("astra.yaml", "/universes/u1/decisions", "decision9"),
        ("astra.yaml", "/universes/u1/decisions", "sub.decision9"),
        ("astra.yaml", "/universes/imp1/analysis", None),
        ("astra.yaml", "/universes/imp2/universe", None),
        ("astra.yaml", "/universes/imp3/universe", None),
        ("astra.yaml", "/universes/imp4/analysis", None),
        ("astra.yaml", "/findings/insight1/evidence/0/artifact", None),
        ("sub/astra.yaml", "/outputs/output1/inputs/1", None),
    ]


def test_it_is_reported_where_it_is_written(broken: api.ValidationReport) -> None:
    """At the value, or for a key of Universe.decisions at its map, naming the key (design §3,
    Annex D)."""
    found = {
        (d.location.pointer, d.location.key): d
        for d in broken.diagnostics
        if d.code == "UNRESOLVED_ADDRESS" and d.location.file == "astra.yaml"
    }
    entry = found["/outputs/output1/inputs/1", None]
    assert (entry.level, entry.location.line, entry.location.column) == ("error", 18, 22)
    assert "`sub` has no input or output `output9`" in entry.message
    key = found["/universes/u1/decisions", "sub.decision9"]
    assert (key.location.line, key.location.column) == (24, 45)
    assert (
        "this file declares no analysis `nothere`"
        in found["/outputs/output1/inputs/2", None].message
    )


def test_an_import_names_another_analysiss_universe(broken: api.ValidationReport) -> None:
    """§12 *Imports*: never an import in its file, nor a universe of the
    importing analysis itself."""
    found = {d.location.pointer: d.message for d in broken.diagnostics}
    assert "`sub` has no universe `sub_v1`" in found["/universes/imp3/universe"]
    assert "leads back to this one" in found["/universes/imp4/analysis"]


def test_every_field_keeps_it_where_its_address_resolves(tmp_path: Path) -> None:
    """§6, §15: through two spellings of `sub`, `self: {path: .}`, and `sub`'s `..` back to the
    root; and an import whose `analysis` leads through the parent to a sibling (§16)."""
    files = {"astra.yaml": KEPT, "sub/astra.yaml": SUB % "output1"}
    assert unresolved(api.validate(repository(tmp_path, files))) == []


@pytest.mark.parametrize(
    ("analyses", "outcome"),
    [
        ("{sub: {path: nothere}}", "MISSING_DECLARED_ANALYSIS"),
        ("{sub: {path: ..}}", "DECLARATION_OUTSIDE_REPOSITORY"),
        ("{sub: {path: bad}}", "UNKNOWN_FIELD"),
        (f"{{sub: {{url: 'file:///nowhere/r.git', commit: '{'0' * 40}'}}}}", "REMOTE_UNREACHABLE"),
    ],
)
def test_no_address_through_an_undetermined_analysis_is_checked(
    tmp_path: Path, analyses: str, outcome: str | None
) -> None:
    """design §4.13 case 4: in the files that declare an undetermined analysis, no address through
    that declaration is checked; the declaration's own code is reported."""
    text = (
        KEPT.replace(
            "analyses:\n  sub: {path: sub}\n  again: {path: ./sub/}\n  self: {path: .}\n",
            f"analyses: {analyses}\n",
        )
        .replace("again.", "sub.")
        .replace("self.", "")
    )
    files = {
        "astra.yaml": text,
        "data/input1.csv": "1\n",
        "bad/astra.yaml": SUB % "output1" + "name: x\n",
    }
    report = api.validate(repository(tmp_path, files))
    assert unresolved(report) == []
    assert [d.code for d in report.diagnostics] == ([outcome] if outcome else [])
