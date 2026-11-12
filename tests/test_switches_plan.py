"""Switches in the plan, the view and the check (design §4.6, §4.7, §4.11): a result read
through a switch (Elements *takes*; Results *plans*, *made from*, *Evidence*), the plan's note
on an output a switch leaves unbuilt, what a universe uses and what is built there, and what a
switch makes stale.

The stacks are `tests.test_switches`' running example, its nested switches and its switch
between declared analyses; a switch whose cases are each taken in one universe, or none; and
one two of whose options share a case, built as a runner builds it (`conftest.build`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.check import CheckReport
from astra.cli import main
from astra.plan import Plan, render_command
from astra.plan import Result as Planned
from astra.stack import Element
from tests.conftest import build, repository
from tests.test_switches import CHOOSING_FILES, NESTED_FILES, ROOT, RUNNING_FILES, variant


def astra(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


def results(plan: Plan) -> set[tuple[str, str]]:
    """Each result: the analysis it belongs to, and its addresses (Results)."""
    return {(str(r.owner), ", ".join(p.address for p in r.places)) for r in plan.results}


def result(plan: Plan, address: str) -> Planned:
    """The result whose first place has `address`."""
    (found,) = [r for r in plan.results if r.places[0].address == address]
    return found


@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("running"), RUNNING_FILES)


# --- C. the plan ---


def test_the_running_example_plans_what_results_lists(running: Path) -> None:
    """Results: the planned results are `output2`, `output1` in `u1` and `u2`, `output6` in
    `u1`, `stage.output3` in `u1`, `u2` and `v1`, and `upstream.output4`; `output6` isn't built
    in `u2`, where `switch1` has no case for `a`."""
    assert results(api.plan(running)) == {
        (".", "output2"),
        (".", "output1#u1"),
        (".", "output1#u2"),
        (".", "output6#u1"),
        (".", "stage.output3#u1"),
        (".", "stage.output3#u2"),
        ("stage", "output3#v1"),
        ("upstream", "output4"),
    }


def test_an_entry_naming_a_switch_reads_the_case_it_takes(running: Path) -> None:
    """Elements: where `decision1` selects `b`, `switch1` takes `stage.output3`, and
    `{inputs.switch1}` is the path of its result there. The read says which case it went
    through (`via`), as written."""
    plan = api.plan(running)
    six = result(plan, "output6#u1")
    (read,) = six.inputs
    assert (read.entry, read.path, read.commit, read.via) == (
        "switch1",
        "results/u1/stage.output3.csv",
        None,
        ("stage.output3",),
    )
    assert read.result == result(plan, "stage.output3#u1")
    assert render_command(six, running) == (
        "python src/output6.py 'results/u1/stage.output3.csv' 'a' 'results/u1/output6.png'"
    )
    assert [read.via for read in result(plan, "output1#u1").inputs] == [(), (), ()]


def test_the_plan_notes_an_output_a_switch_leaves_unbuilt(running: Path) -> None:
    """Design §4.6: the plan says which outputs aren't built in which universe, and why: the
    switch with no case there, and the option its decision selects. A missing case breaks no
    rule."""
    (note,) = [n for n in api.plan(running).notes if n.kind == "not_built"]
    assert note.location is not None
    assert (note.location.file, note.location.pointer) == ("astra.yaml", "/outputs/output6")
    assert note.universes == (Element(ROOT, "universe", "u2"),)
    assert (note.switch, note.option) == (Element(ROOT, "switch", "switch1"), "a")
    assert (note.results, note.built) == ((), True)
    assert "has no case" in note.message


def test_the_plan_as_astra_plan_1_reads_through_switches(running: Path) -> None:
    """Design §4.11: each read says which cases it went through (`via`), and each note which
    universes, switch and option it concerns, none for a note of another kind."""
    shape = api.plan(running).to_json()
    index = {
        ", ".join(place["address"] for place in found["places"]): at
        for at, found in enumerate(shape["results"])
    }
    assert shape["results"][index["output6#u1"]]["inputs"] == [
        {
            "entry": "switch1",
            "path": "results/u1/stage.output3.csv",
            "commit": None,
            "result": index["stage.output3#u1"],
            "via": ["stage.output3"],
        }
    ]
    assert [read["via"] for read in shape["results"][index["output1#u1"]]["inputs"]] == [[]] * 3
    (note,) = [n for n in shape["notes"] if n["kind"] == "not_built"]
    root = {"folder": "", "commit": None}
    assert {key: note[key] for key in ("universes", "switch", "option", "results", "built")} == {
        "universes": [{"analysis": root, "id": "u2"}],
        "switch": {"analysis": root, "id": "switch1"},
        "option": "a",
        "results": [],
        "built": True,
    }
    assert note["location"]["pointer"] == "/outputs/output6"
    others = [n for n in shape["notes"] if n["kind"] != "not_built"]
    assert others
    assert all((n["universes"], n["switch"], n["option"]) == ([], None, None) for n in others)


@pytest.fixture(scope="module")
def nested(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("nested"), NESTED_FILES)


def test_nested_switches_read_through_each_case_they_take(nested: Path) -> None:
    """Elements: a case that names a switch nests the two, and reading the outer reads what the
    inner takes, in the universe the case is read in; a pinned case reads its target as built in
    its pin's universe; a case on an input reads the input's file."""
    plan = api.plan(nested)
    assert results(plan) == {
        (".", "reader#ua"),
        (".", "reader#ub"),
        (".", "reader#uc"),
        (".", "reader#w"),
        (".", "fit#ua"),
        (".", "fit#w"),
    }
    reads = {
        found.places[0].address: [(read.entry, read.path, read.via) for read in found.inputs]
        for found in plan.results
        if found.output.id == "reader"
    }
    assert reads == {
        "reader#ua": [("outer", "results/ua/fit.json", ("inner", "fit"))],
        "reader#ub": [("outer", "results/w/fit.json", ("fit#w",))],
        "reader#uc": [("outer", "data/input1.csv", ("input1",))],
        "reader#w": [("outer", "data/input1.csv", ("inner", "input1"))],
    }
    assert result(plan, "reader#ub").inputs[0].result == result(plan, "fit#w")
    assert result(plan, "reader#uc").inputs[0].result is None
    assert render_command(result(plan, "reader#uc"), nested) == (
        "python read.py 'data/input1.csv' 'results/uc/reader.csv'"
    )


TAKEN = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}, c: {}}
outputs:
  out_a:
    type: metric
    format: json
    decisions: [decision1]
    recipe:
      command: python make.py '{decisions.decision1}' '{output}'
  out_b:
    type: metric
    format: json
    decisions: [decision1]
    recipe:
      command: python make.py '{decisions.decision1}' '{output}'
  out_c:
    type: metric
    format: json
    decisions: [decision1]
    recipe:
      command: python make.py '{decisions.decision1}' '{output}'
  sw:
    switch: decision1
    cases: {a: out_a, b: out_b, c: out_c}
universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: b}
"""
"""`sw`, which nothing reads, takes `out_a` in `u1` and `out_b` in `u2`; no universe selects
`c`."""


def test_an_output_a_case_names_is_planned_only_where_it_is_taken(tmp_path: Path) -> None:
    """Results *plans*: the driving analysis plans from its own switches that nothing of its own
    reads, and from its own outputs that no case of its own names, so `sw` plans the case it
    takes where it is built, and `out_a`, `out_b` and `out_c` only there. `out_c`, never taken,
    has no planned result, which the plan notes (design §4.6)."""
    plan = api.plan(repository(tmp_path, {"astra.yaml": TAKEN}))
    assert results(plan) == {(".", "out_a#u1"), (".", "out_b#u2")}
    (note,) = [n for n in plan.notes if n.kind == "unplanned"]
    assert note.location is not None
    assert note.location.pointer == "/outputs/out_c"
    assert "only a case of `sw`" in note.message
    assert note.built


def test_an_output_a_case_names_is_built_everywhere_once_cited(tmp_path: Path) -> None:
    """Results *plans*: one that is also a deliverable must be read or cited elsewhere to be
    built where that case isn't taken. A finding citing `out_c` plans it in each universe."""
    text = TAKEN + (
        "findings:\n  finding1:\n    claim: c is reported.\n    evidence:\n"
        "      - artifact: out_c\n"
    )
    plan = api.plan(repository(tmp_path, {"astra.yaml": text}))
    assert results(plan) == {
        (".", "out_a#u1"),
        (".", "out_b#u2"),
        (".", "out_c#u1"),
        (".", "out_c#u2"),
    }
    assert [n for n in plan.notes if n.kind == "unplanned"] == []


@pytest.fixture(scope="module")
def choosing(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("choosing"), CHOOSING_FILES)


def test_a_switch_between_analyses_plans_the_one_it_takes(choosing: Path) -> None:
    """Elements: a switch can choose between analyses. `refined` reads `fast.fit` in `q` and
    `slow.fit` in `c`; in `m`, `model` has no case for `manual`, so nothing is planned there,
    and the plan says so; `report` and `tools.helper` are built once."""
    plan = api.plan(choosing)
    assert results(plan) == {
        (".", "refined#q"),
        (".", "fast.fit#q"),
        (".", "refined#c"),
        (".", "slow.fit#c"),
        (".", "report"),
        ("tools", "helper"),
    }
    assert [r for r in plan.results if r.universe is not None and r.universe.id == "m"] == []
    assert [(read.entry, read.path, read.via) for read in result(plan, "refined#q").inputs] == [
        ("model", "results/q/fast.fit.csv", ("fast.fit",)),
        ("tools.helper", "tools/results/helper.csv", ()),
    ]
    (note,) = [n for n in plan.notes if n.kind == "not_built"]
    assert note.location is not None
    assert note.location.pointer == "/outputs/refined"
    assert note.universes == (Element(ROOT, "universe", "m"),)
    assert (note.switch, note.option) == (Element(ROOT, "switch", "model"), "manual")


def test_a_switch_asked_for_is_a_request_error(running: Path) -> None:
    """Elements: a switch has no result of its own, so it can't be asked for."""
    with pytest.raises(api.RequestError, match="is a switch"):
        api.plan(running, outputs=["switch1"])


GAP = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  base:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  gap:
    switch: decision1
    cases: {b: base}
  reader:
    type: metric
    format: json
    inputs: [gap]
    recipe:
      command: python read.py '{inputs.gap}' '{output}'
universes:
  u1:
    decisions: {decision1: a}
"""
"""`gap` takes nothing in `u1`, the root's only universe, so `reader` is built in none."""


def test_an_output_built_in_none_of_the_roots_universes_has_no_result_to_give(
    tmp_path: Path,
) -> None:
    """Results *built*: `reader` reads `gap` without a pin, and `gap` has no case for `a`, so it
    has no planned result, which the plan notes twice (design §4.6), and asked for, it has none
    to give; `base`, which only a case of `gap` names, is planned only where something planned
    reads it."""
    top = repository(tmp_path, {"astra.yaml": GAP})
    plan = api.plan(top)
    assert results(plan) == set()
    unplanned = {
        n.location and n.location.pointer: n.message for n in plan.notes if n.kind == "unplanned"
    }
    assert unplanned == {
        "/outputs/base": "`base` has no planned result: only a case of `gap` names it, so it is "
        "planned only where something planned reads it, and nothing does, so a check of the root "
        "never covers it",
        "/outputs/reader": "`reader` has no planned result: it is built in none of the root's "
        "universes, so a check of the root never covers it",
    }
    (note,) = [n for n in plan.notes if n.kind == "not_built"]
    assert note.message == (
        "`reader` isn't built in `u1`: `gap` has no case there for `a`, the option its decision "
        "selects"
    )
    lines = astra("plan", str(top)).stdout.splitlines()
    assert "  1 output(s) aren't built in some universe, where a switch has no case" in lines
    with pytest.raises(api.RequestError, match="^`reader` has no result in the root's universes"):
        api.plan(top, outputs=["reader"])
    assert results(api.plan(top, outputs=["base"])) == {(".", "base")}


ROOTED = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}, c: {}}
  decision2:
    options: {x: {}, y: {}}
outputs:
  base:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  gap:
    switch: decision1
    cases: {b: base, c: inner}
  inner:
    switch: decision2
    cases: {x: base}
universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: b}
  u3:
    decisions: {decision1: c, decision2: y}
"""
"""`gap`, which nothing reads, takes nothing in `u1` and, through `inner`, nothing in `u3`."""


def test_the_plan_notes_a_switch_nothing_reads_where_it_takes_nothing(tmp_path: Path) -> None:
    """Design §4.6: a switch the plan plans from, which nothing reads (Results *plans*), gets a
    `not_built` note where it takes nothing, as an output does: `gap` has no case for `a` in
    `u1`, and in `u3` takes `inner`, which has no case for `y`. `inner`, which `gap`'s case
    reads, is left to `gap`'s note."""
    plan = api.plan(repository(tmp_path, {"astra.yaml": ROOTED}))
    assert results(plan) == {(".", "base")}
    notes = [n for n in plan.notes if n.kind == "not_built"]
    found = [
        (n.location and n.location.pointer, [u.id for u in n.universes], n.switch, n.option)
        for n in notes
    ]
    assert found == [
        ("/outputs/gap", ["u1"], Element(ROOT, "switch", "gap"), "a"),
        ("/outputs/gap", ["u3"], Element(ROOT, "switch", "inner"), "y"),
    ]
    assert [n.message for n in notes] == [
        "`gap` isn't built in `u1`: it has no case there for `a`, the option its decision selects",
        "`gap` isn't built in `u3`: `inner` has no case there for `y`, the option its decision "
        "selects",
    ]


# --- D. the view ---


def test_the_view_says_what_a_universe_uses_and_what_is_built_there(running: Path) -> None:
    """Results *uses* and *built*: `u2` selects `a` for `decision3`, inherited, but doesn't use
    it, as `output6` isn't built there: `switch1` takes nothing. In `u1`, it takes
    `stage.output3`."""
    two = api.view("u2", running).analyses[0]
    assert (two.decisions["decision3"].used, two.decisions["decision3"].selected) == (False, "a")
    assert (two.decisions["decision1"].used, two.decisions["decision1"].selected) == (True, "a")
    assert (two.outputs["output6"].built, two.outputs["output6"].result) == (False, None)
    assert (two.outputs["switch1"].built, two.outputs["switch1"].takes) == (False, None)
    one = api.view("u1", running).analyses[0]
    assert (one.outputs["switch1"].built, one.outputs["switch1"].takes) == (True, "stage.output3")
    assert one.outputs["output6"].built is True
    assert one.decisions["decision3"].used is True


def test_the_view_as_astra_universe_view_1_says_what_is_used_built_and_taken(
    running: Path,
) -> None:
    """Design §4.11: a decision's `used` and `selected`; an output's `built`, `takes` (a
    switch's) and `result`."""
    shape = api.view("u2", running).to_json()
    for analysis in shape["analyses"]:
        assert all(set(d) == {"used", "selected"} for d in analysis["decisions"].values())
        assert all(set(o) == {"built", "takes", "result"} for o in analysis["outputs"].values())
    root = shape["analyses"][0]
    assert root["decisions"]["decision3"] == {"used": False, "selected": "a"}
    assert root["outputs"]["output6"] == {"built": False, "takes": None, "result": None}
    assert root["outputs"]["switch1"] == {"built": False, "takes": None, "result": None}
    one = api.view("u1", running).to_json()["analyses"][0]
    assert one["outputs"]["switch1"] == {"built": True, "takes": "stage.output3", "result": None}


def test_astra_view_shows_what_each_switch_takes(running: Path) -> None:
    two = astra("view", "u2", str(running))
    assert two.exit_code == 0
    lines = two.stdout.splitlines()
    assert "  decision3    a  (unused)" in lines
    assert "  switch1      takes nothing" in lines
    assert "  output6      not built" in lines
    one = astra("view", "u1", str(running))
    assert one.exit_code == 0
    assert "  switch1      takes stage.output3" in one.stdout.splitlines()


# --- E. the check ---

CHECKED = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}, c: {}}
outputs:
  base:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  other:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  sw:
    switch: decision1
    cases: {a: base, b: base, c: other}
  reader:
    type: metric
    format: json
    inputs: [sw]
    recipe:
      command: python read.py '{inputs.sw}' '{output}'
universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: c}
findings:
  finding1:
    claim: The reader reads the case the switch takes.
    evidence:
      - artifact: sw
"""
"""`a` and `b` share `sw`'s case `base`; `reader` reads `base` in `u1` and `other` in `u2`."""

UNCHANGED = {
    "base": ("unchanged", "present"),
    "other": ("unchanged", "present"),
    "reader#u1": ("unchanged", "present"),
    "reader#u2": ("unchanged", "present"),
}


def statuses(report: CheckReport) -> dict[str, tuple[str, str | None]]:
    """Each place's address, and its record and bytes statuses."""
    return {
        status.place.address: (status.record_status, status.bytes_status)
        for checked in report.results
        for status in checked.statuses
    }


def messages(report: CheckReport, address: str) -> list[str]:
    return [
        reason.message
        for checked in report.results
        for status in checked.statuses
        if status.place.address == address
        for reason in status.reasons
    ]


@pytest.fixture(scope="module")
def committed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`CHECKED`, built from its commit with the same bytes for every result, its records and
    bytes then committed."""
    top = repository(tmp_path_factory.mktemp("checked"), {"astra.yaml": CHECKED})
    build(top, made=lambda _: b"same\n")
    return repository(top, {})


@pytest.fixture
def checked(committed: Path, tmp_path: Path) -> Path:
    """A copy of `committed` of the test's own."""
    return Path(shutil.copytree(committed, tmp_path / "checked", symlinks=True))


def test_results_read_through_a_switch_are_unchanged_where_nothing_changed(checked: Path) -> None:
    report = api.check(checked)
    assert statuses(report) == UNCHANGED
    assert report.ok


def test_another_option_selected_for_a_switchs_decision_makes_its_reader_stale(
    checked: Path,
) -> None:
    """Results *made from*: for each switch it reads through, the decision it switches on and
    the option selected for it where it is read, whatever bytes result. `u1` selects `b`,
    whose case is `base` too: `reader` in `u1` reads the same result, and is stale."""
    (checked / "astra.yaml").write_text(
        variant(CHECKED, ("{decision1: a}", "{decision1: b}")), "utf-8"
    )
    report = api.check(checked)
    assert statuses(report) == {**UNCHANGED, "reader#u1": ("stale", "present")}
    assert any("switches on" in message for message in messages(report, "reader#u1"))


def test_another_case_taken_makes_its_reader_stale(checked: Path) -> None:
    """Results *made from*: the case a switch takes, whatever bytes result. `sw`'s case for `a`
    becomes `other`, which has `base`'s bytes; `base`, which no universe now takes, isn't
    planned."""
    text = variant(CHECKED, ("{a: base, b: base, c: other}", "{a: other, b: base, c: other}"))
    (checked / "astra.yaml").write_text(text, "utf-8")
    report = api.check(checked)
    assert statuses(report) == {
        "other": ("unchanged", "present"),
        "reader#u1": ("stale", "present"),
        "reader#u2": ("unchanged", "present"),
    }
    assert any("case for" in message for message in messages(report, "reader#u1"))


def test_evidence_citing_a_switch_cites_the_case_it_takes_in_each_universe(
    checked: Path,
) -> None:
    """Results *Evidence*: citing a switch without a pin, it cites the result in each of the
    driving analysis's universes of the case the switch takes there, and gets the worst of
    their statuses."""
    report = api.check(checked)
    assert [(e.artifact, e.cites, e.record_status) for e in report.evidence] == [
        ("sw", ("base", "other"), "unchanged")
    ]
    (checked / ".astra" / "records" / "other.json").unlink()
    report = api.check(checked)
    assert [(e.artifact, e.cites, e.record_status) for e in report.evidence] == [
        ("sw", ("base", "other"), "missing")
    ]


def test_evidence_citing_a_switch_that_takes_nothing_is_missing(checked: Path) -> None:
    """Results *Evidence*: none means `missing`. `gap` has a case for `b` only, which no
    universe selects."""
    text = variant(
        CHECKED, ("  reader:\n", "  gap:\n    switch: decision1\n    cases: {b: base}\n  reader:\n")
    ) + ("  finding2:\n    claim: The gap is cited.\n    evidence:\n      - artifact: gap\n")
    (checked / "astra.yaml").write_text(text, "utf-8")
    report = api.check(checked)
    assert {e.artifact: (e.cites, e.record_status) for e in report.evidence} == {
        "sw": (("base", "other"), "unchanged"),
        "gap": ((), "missing"),
    }
    assert statuses(report) == UNCHANGED
