"""§6 Names: `UNRESOLVED_ADDRESS`, in every field §6's table lists, a switch's `switch` and cases
too, and in an `artifact` that names a switch with a case on an input (Rules), with design §4.13
cases 4, 5 and 13.

The breaking cases share one stack, whose every address names nothing but the switch an
`artifact` cites; the keeping ones another, whose every address resolves, through spellings,
`self: {path: .}` and `..` too (§15)."""

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
  switch9:
    switch: nothere
    cases: {a: nothing}
  gate:
    switch: decision1
    cases: {a: output1, b: on_input}
  on_input:
    switch: decision1
    cases: {a: output1, b: input1}
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
    evidence: [{artifact: input1}, {artifact: gate}]
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
        ("astra.yaml", "/outputs/switch9/switch", None),
        ("astra.yaml", "/outputs/switch9/cases/a", None),
        ("astra.yaml", "/universes/u1/decisions", "decision9"),
        ("astra.yaml", "/universes/u1/decisions", "sub.decision9"),
        ("astra.yaml", "/universes/imp1/analysis", None),
        ("astra.yaml", "/universes/imp2/universe", None),
        ("astra.yaml", "/universes/imp3/universe", None),
        ("astra.yaml", "/universes/imp4/analysis", None),
        ("astra.yaml", "/findings/insight1/evidence/0/artifact", None),
        ("astra.yaml", "/findings/insight1/evidence/1/artifact", None),
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
    assert (key.location.line, key.location.column) == (33, 45)
    assert (
        "this file declares no analysis `nothere`"
        in found["/outputs/output1/inputs/2", None].message
    )


def test_a_switch_names_a_decision_and_its_cases_an_input_or_output(
    broken: api.ValidationReport,
) -> None:
    """Rules `UNRESOLVED_ADDRESS`: a `switch` names a decision, and a case an input or an output,
    a switch being an output (Elements *switch*); an `artifact` names a switch only where each of
    its cases names an output or a switch like it, nested switches included, reported at the
    `artifact` with the case on an input as related."""
    found = {d.location.pointer: d for d in broken.diagnostics if d.code == "UNRESOLVED_ADDRESS"}
    assert "this analysis has no decision `nothere`" in found["/outputs/switch9/switch"].message
    case = found["/outputs/switch9/cases/a"].message
    assert "this analysis has no input or output `nothing`" in case
    artifact = found["/findings/insight1/evidence/1/artifact"]
    assert "`on_input`'s case for `b`, `input1`, names an input" in artifact.message
    assert [r.pointer for r in artifact.related] == ["/outputs/on_input/cases/b"]


def test_an_import_names_another_analysiss_universe(broken: api.ValidationReport) -> None:
    """§12 *Imports*: never an import in its file, nor a universe of the
    importing analysis itself."""
    found = {d.location.pointer: d.message for d in broken.diagnostics}
    assert "`sub` has no universe `sub_v1`" in found["/universes/imp3/universe"]
    assert "leads back to this one" in found["/universes/imp4/analysis"]


SWITCHES = """\
  switch1:
    switch: sub.decision1
    cases: {a: sub.output1#v1, b: again.output1}
  switch2:
    switch: self.decision1
    cases: {a: switch1, b: self.output2}
  on_inputs:
    switch: decision1
    cases: {a: input1, b: sub.parent.input1}
"""
"""Switches whose `switch` and cases resolve through spellings: `switch2` nests `switch1`, and
every case of either names an output; `on_inputs`'s cases name inputs."""


def test_every_field_keeps_it_where_its_address_resolves(tmp_path: Path) -> None:
    """§6, §15: through two spellings of `sub`, `self: {path: .}`, and `sub`'s `..` back to the
    root; and an import whose `analysis` leads through the parent to a sibling (§16). A switch's
    `switch` and cases too, and an `artifact` that names a switch each of whose cases names an
    output or a switch like it (Elements *switch*, Rules `UNRESOLVED_ADDRESS`)."""
    text = KEPT.replace("universes:\n", SWITCHES + "universes:\n", 1).replace(
        "{artifact: self.output2}]", "{artifact: self.output2}, {artifact: switch2}]"
    )
    files = {"astra.yaml": text, "sub/astra.yaml": SUB % "output1"}
    assert unresolved(api.validate(repository(tmp_path, files))) == []


AMBIGUOUS = """\
spec_version: "0.1.0"
inputs:
  shared: {path: data/shared.csv}
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    inputs: [shared]
    recipe:
      command: python make.py '{output}'
  switch1:
    switch: decision1
    cases: {a: shared, b: output1}
  shared:
    switch: decision1
    cases: {a: output1}
"""


def test_an_id_an_input_and_a_switch_share_breaks_only_ambiguous_id(tmp_path: Path) -> None:
    """design §4.13 case 5: an entry of `inputs`, or a case, whose id is both an input and a
    switch names nothing, as one an input and an output share, and breaks `AMBIGUOUS_ID`, not
    this rule."""
    report = api.validate(repository(tmp_path, {"astra.yaml": AMBIGUOUS}))
    assert unresolved(report) == []
    assert "AMBIGUOUS_ID" in {d.code for d in report.diagnostics}


CYCLING = """\
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
    recipe:
      command: python make.py '{output}'
  switch1:
    switch: decision1
    cases: {a: switch2, b: input1}
  switch2:
    switch: decision1
    cases: {a: switch1, b: output1}
  switch3:
    switch: decision1
    cases: {a: output9, b: input1}
findings:
  insight1:
    claim: The cycle's cause is reported, not this.
    evidence: [{artifact: switch1}, {artifact: switch3}]
"""


def test_an_artifact_on_a_switch_whose_case_names_nothing_or_cycles_isnt_judged(
    tmp_path: Path,
) -> None:
    """design §4.13 cases 5 and 13: a switch with a case that names nothing, or on a cycle, isn't
    judged as an `artifact`, though another case names an input: the case's own cause is
    reported."""
    report = api.validate(repository(tmp_path, {"astra.yaml": CYCLING}))
    assert unresolved(report) == [("astra.yaml", "/outputs/switch3/cases/a", None)]


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
