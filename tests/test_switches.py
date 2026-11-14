"""Switches (Elements *switch*, *takes*), what a universe uses (Results *reaches*, *uses*, *uses
on some branch*), and the validator's rules on them (Rules): `UNRESOLVED_ADDRESS`,
`UNKNOWN_OPTION`, `OUTPUT_CYCLE`, `UNUSED_DECISION`, `INACTIVE_DECISION`, `MISSING_DECISION`,
`MISSING_REQUIRED_OPTION`, `INCOMPATIBLE_OPTIONS`, `PIN_NOT_BUILT`, `NOT_BUILT_IN_UNIVERSE`
and `UNDRIVEN_DECLARATION`, with what a name that names nothing, a switch undetermined in a
universe, a universe with no effective selection and an output on a cycle leave unchecked.

Binding first (`api.bind`), then the validator (`api.validate`). Which files are valid is the
conformance suite's to say; these tests pin astra-tools' own part: where each diagnostic is
reported (its file, pointer and key), its level, and what its message says.

The stacks are Elements' running example with its switch `switch1` and `output6`, reading
`stage` and `upstream`; a switch that chooses between two declared analyses, `fast` and `slow`
(Elements), with a `tools` none of whose decisions anything planned uses; nested switches; and
small stacks, one for each rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

from astra import api
from astra.diagnostics import Catalogue
from astra.rules.context import Context
from astra.stack import Element, Identity
from tests.conftest import MINIMAL, git, repository

ROOT = Identity("")

Seen = tuple[str, str, str, str | None]
"""A diagnostic as these tests compare it: its code, file, pointer and key."""


def ordered(seen: Iterable[Seen]) -> list[Seen]:
    """`seen` in an order of their own, so that a list is compared whatever order the report
    gives."""
    return sorted(seen, key=lambda s: (s[0], s[1], s[2], s[3] or ""))


def found(report: api.ValidationReport) -> list[Seen]:
    """Every diagnostic of `report`."""
    return ordered(
        (d.code, d.location.file, d.location.pointer, d.location.key) for d in report.diagnostics
    )


def validated(top: Path, files: Mapping[str, str]) -> api.ValidationReport:
    """The report on the stack of `files`, committed in a repository at `top`."""
    return api.validate(repository(top, files))


def output(id_: str, inputs: str | None = None, decisions: str | None = None) -> str:
    """An entry of `outputs`, `id_`, with `inputs` and `decisions` (flow lists) where given."""
    text = f"  {id_}:\n    type: metric\n    format: json\n"
    if inputs is not None:
        text += f"    inputs: {inputs}\n"
    if decisions is not None:
        text += f"    decisions: {decisions}\n"
    return text + "    recipe:\n      command: python make.py '{output}'\n"


def switch(id_: str, decision: str, cases: str) -> str:
    """An entry of `outputs` that is a switch on `decision`, with `cases` (a flow map)."""
    return f"  {id_}:\n    switch: {decision}\n    cases: {cases}\n"


# --- Elements' running example ---

RUNNING = """\
spec_version: "0.1.0"
analyses:
  stage: {path: stage}
  upstream: {path: upstream}
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options:
      a: {}
      b:
        requires: [stage.decision2.b]
      c:
        excluded: It needs data this analysis doesn't have.
  decision3:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    inputs: [input1, stage.output3, upstream.output4]
    decisions: [decision1, stage.decision2]
    recipe:
      command: >-
        python src/output1.py '{inputs.input1}' '{inputs.stage.output3}'
        '{inputs.upstream.output4}' '{decisions.decision1}' '{decisions.stage.decision2}'
        '{output}'
  output2:
    type: table
    format: csv
    inputs: [output1#u1, output1#u2, stage.output3#v1]
    recipe:
      command: python src/output2.py {inputs} '{output}'
  switch1:
    switch: decision1
    cases:
      b: stage.output3
  output6:
    type: figure
    format: png
    inputs: [switch1]
    decisions: [decision3]
    recipe:
      command: python src/output6.py '{inputs.switch1}' '{decisions.decision3}' '{output}'
universes:
  u1:
    decisions:
      decision1: b
      decision3: a
      stage.decision2: b
  u2:
    derived_from: u1
    decisions: {decision1: a}
findings:
  insight1:
    claim: The two universes give different results.
    evidence:
      - artifact: output2
"""
"""Elements' `analysis`, with its switch: `switch1` takes `stage.output3` in `u1`, where
`decision1` selects `b`, and nothing in `u2`, where it selects `a`, so `output6`, which reads it
without a pin and lists `decision3`, is built in `u1` alone."""

RUNNING_STAGE = """\
spec_version: "0.1.0"
inputs:
  input2: {path: data/input2.csv}
decisions:
  decision2:
    options: {a: {}, b: {}}
outputs:
  output3:
    type: data
    format: csv
    inputs: [input2]
    decisions: [decision2]
    recipe:
      command: python src/output3.py '{inputs.input2}' '{decisions.decision2}' '{output}'
universes:
  v1:
    decisions: {decision2: a}
"""

RUNNING_UPSTREAM = """\
spec_version: "0.1.0"
outputs:
  output4:
    type: data
    format: csv
    recipe:
      command: python src/output4.py '{output}'
"""
"""`upstream`, by path here: its `output4` is built once."""

RUNNING_FILES = {
    "astra.yaml": RUNNING,
    "data/input1.csv": "1\n",
    "stage/astra.yaml": RUNNING_STAGE,
    "stage/data/input2.csv": "2\n",
    "upstream/astra.yaml": RUNNING_UPSTREAM,
}


@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return repository(tmp_path_factory.mktemp("running"), RUNNING_FILES)


# --- nested switches, a pinned case and a case on an input ---

NESTED = """\
spec_version: "0.1.0"
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options: {a: {}, b: {}, c: {}}
  decision2:
    options: {x: {}, y: {}}
outputs:
  fit:
    type: metric
    format: json
    decisions: [decision2]
    recipe:
      command: python fit.py '{decisions.decision2}' '{output}'
  inner:
    switch: decision2
    cases: {x: fit, y: input1}
  outer:
    label: The outer switch
    switch: decision1
    cases: {a: inner, b: fit#w, c: input1}
  reader:
    type: table
    format: csv
    inputs: [outer]
    recipe:
      command: python read.py '{inputs.outer}' '{output}'
universes:
  ua:
    decisions: {decision1: a, decision2: x}
  ub:
    decisions: {decision1: b}
  uc:
    decisions: {decision1: c}
  w:
    decisions: {decision1: a, decision2: y}
"""
"""`outer` nests `inner`, whose decision matters only where `outer` takes it: `reader` reads
`fit` in `ua` through both, `fit` as built in `w` in `ub`, through a pinned case, and `input1`
in `uc` and `w`."""

NESTED_FILES = {"astra.yaml": NESTED, "data/input1.csv": "1\n"}


# --- a switch that chooses between declared analyses ---

CHOOSING = """\
spec_version: "0.1.0"
analyses:
  fast: {path: fast}
  slow: {path: slow}
  tools: {path: tools}
decisions:
  method: {options: {quick: {}, careful: {}, manual: {}}}
  prior: {options: {flat: {}, informed: {}}}
outputs:
  model:
    switch: method
    cases: {quick: fast.fit, careful: slow.fit}
  refined:
    type: data
    format: csv
    inputs: [model, tools.helper]
    decisions: [prior]
    recipe:
      command: python refine.py {inputs} {decisions.prior} {output}
  report:
    type: report
    format: pdf
    inputs: [refined#q]
    recipe:
      command: python report.py {inputs} {output}
universes:
  q: {decisions: {method: quick, prior: flat, fast.decision5: x}}
  c: {decisions: {method: careful, prior: flat, slow.decision5: y}}
  m: {decisions: {method: manual}}
"""
"""`model` takes `fast.fit` in `q`, `slow.fit` in `c` and nothing in `m`, where `method`
selects `manual`, which has no case: `refined` is built in `q` and `c` only, and `m` uses
`method` alone. `report`, built once, pins `refined` in `q`."""

FIT = """\
spec_version: "0.1.0"
decisions:
  decision5:
    options: {x: {}, y: {}}
outputs:
  fit:
    type: data
    format: csv
    decisions: [decision5]
    recipe:
      command: python fit.py {decisions.decision5} {output}
"""
"""`fast` and `slow`: each an output `fit` listing a `decision5` of its own."""

TOOLS = """\
spec_version: "0.1.0"
decisions:
  decision6:
    options: {p: {}, r: {}}
outputs:
  helper:
    type: data
    format: csv
    recipe:
      command: python helper.py {output}
  unused:
    type: data
    format: csv
    decisions: [decision6]
    recipe:
      command: python unused.py {decisions.decision6} {output}
"""
"""`tools`: `helper`, built once, and `unused`, the only user of `decision6`, which nothing
reads."""

CHOOSING_FILES = {
    "astra.yaml": CHOOSING,
    "fast/astra.yaml": FIT,
    "slow/astra.yaml": FIT,
    "tools/astra.yaml": TOOLS,
}


def variant(text: str, *edits: tuple[str, str]) -> str:
    """`text` with each `(old, new)` of `edits` replaced, each `old` found exactly once."""
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


# --- A. binding ---


def test_a_switch_is_an_element_of_its_own_kind(running: Path) -> None:
    """Elements: a switch is an entry of `outputs`, bound as an element of kind `switch`, never
    `output`: it has no result, record, name or place of its own. An `inputs` entry may name
    one."""
    stack = api.bind(running).stack
    assert stack is not None
    switch1 = Element(ROOT, "switch", "switch1")
    assert stack.element("switch1", "switch") == switch1
    assert stack.element("switch1", "output") is None
    assert stack.element("output6", "output") == Element(ROOT, "output", "output6")
    (entry,) = [r for r in stack.resolutions if r.pointer == ("outputs", "output6", "inputs", 0)]
    assert (entry.field, entry.written, entry.element) == ("inputs", "switch1", switch1)
    assert set(stack.switches) == {switch1}


def test_a_switchs_decision_and_cases_are_resolved_where_they_are_written(
    tmp_path: Path,
) -> None:
    """Elements: a switch's `switch` is a decision's address, and each value of its `cases` a
    reference, to an input, an output or a switch, which may be pinned. Each is resolved, its
    switch its owner: `switch` first, then each case in the order written, keyed by its option."""
    stack = api.bind(repository(tmp_path, NESTED_FILES)).stack
    assert stack is not None
    outer = Element(ROOT, "switch", "outer")
    written = [r for r in stack.resolutions if r.owner == outer]
    assert [(r.field, r.pointer, r.written, r.option, r.pin, r.element) for r in written] == [
        (
            "switch",
            ("outputs", "outer", "switch"),
            "decision1",
            None,
            None,
            Element(ROOT, "decision", "decision1"),
        ),
        (
            "case",
            ("outputs", "outer", "cases", "a"),
            "inner",
            "a",
            None,
            Element(ROOT, "switch", "inner"),
        ),
        (
            "case",
            ("outputs", "outer", "cases", "b"),
            "fit#w",
            "b",
            "w",
            Element(ROOT, "output", "fit"),
        ),
        (
            "case",
            ("outputs", "outer", "cases", "c"),
            "input1",
            "c",
            None,
            Element(ROOT, "input", "input1"),
        ),
    ]
    resolved = stack.switches[outer]
    assert resolved.decision == written[0]
    assert dict(resolved.cases) == {"a": written[1], "b": written[2], "c": written[3]}
    assert set(stack.switches) == {outer, Element(ROOT, "switch", "inner")}


# --- B. the validator ---

NAMES = """\
spec_version: "0.1.0"
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options:
      a: {}
      b: {}
      c:
        excluded: It isn't what this analysis is for.
outputs:
  output1:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
"""
"""An analysis with no universes, to which each case below adds outputs, and findings."""

FINDING = """\
findings:
  finding1:
    claim: The switch is cited.
    evidence:
      - artifact: %s
"""


@pytest.mark.parametrize(
    "added, expected",
    [
        (switch("s", "nothere", "{a: output1}"), [("/outputs/s/switch", None)]),
        (switch("s", "output1", "{a: output1}"), [("/outputs/s/switch", None)]),
        (switch("s", "decision1", "{a: nothing, b: output1}"), [("/outputs/s/cases/a", None)]),
        (
            switch("s", "decision1", "{a: input1, b: output1}") + FINDING % "s",
            [("/findings/finding1/evidence/0/artifact", None)],
        ),
        (
            switch("s", "decision1", "{a: input1, b: output1}")
            + switch("t", "decision1", "{a: s, b: output1}")
            + FINDING % "t",
            [("/findings/finding1/evidence/0/artifact", None)],
        ),
        (
            switch("s", "decision1", "{a: nothing, b: input1}") + FINDING % "s",
            [("/outputs/s/cases/a", None)],
        ),
    ],
    ids=[
        "switch-names-nothing",
        "switch-names-an-output",
        "case-names-nothing",
        "evidence-on-a-switch-with-a-case-on-an-input",
        "evidence-on-a-switch-nesting-one-with-a-case-on-an-input",
        "evidence-on-a-switch-whose-case-names-nothing",
    ],
)
def test_unresolved_address_at_a_switch(
    tmp_path: Path, added: str, expected: list[tuple[str, str | None]]
) -> None:
    """Rules, `UNRESOLVED_ADDRESS`: a switch's `switch` names a decision, and no output; each of
    its `cases` an input or an output (a switch is one); and an `artifact` naming a switch needs
    each of its cases, through nested switches, to name an output other than a switch. Where a
    case names nothing, that is what is reported, and the evidence citing the switch isn't
    judged."""
    report = validated(tmp_path, {"astra.yaml": NAMES + added, "data/input1.csv": "1\n"})
    assert found(report) == ordered(
        ("UNRESOLVED_ADDRESS", "astra.yaml", pointer, key) for pointer, key in expected
    )


@pytest.mark.parametrize(
    "added",
    [
        switch("s", "decision1", "{a: input1, b: output1}") + output("reader", "[s]"),
        switch("s", "decision1", "{a: output1, c: output1}") + FINDING % "s",
    ],
    ids=["an-output-reads-a-switch-with-a-case-on-an-input", "evidence-on-a-switch-of-outputs"],
)
def test_switches_naming_what_they_may_keep_unresolved_address(tmp_path: Path, added: str) -> None:
    """Elements: a case names an input, an output or a switch; options may share a case, and a
    case may name an excluded option (`c`). Evidence may cite a switch whose cases name
    outputs."""
    report = validated(tmp_path, {"astra.yaml": NAMES + added, "data/input1.csv": "1\n"})
    assert found(report) == []


def test_a_case_keyed_by_no_option_breaks_unknown_option(tmp_path: Path) -> None:
    """Rules, `UNKNOWN_OPTION`: each key of `cases` is an option of the switch's decision. It is
    reported at `cases`, keyed by the option misspelled; a case on the excluded `c` keeps the
    rule."""
    added = switch("s", "decision1", "{a: output1, z: output1}")
    report = validated(tmp_path / "broken", {"astra.yaml": NAMES + added, "data/input1.csv": ""})
    assert found(report) == [("UNKNOWN_OPTION", "astra.yaml", "/outputs/s/cases", "z")]
    (diagnostic,) = report.diagnostics
    assert diagnostic.level == "error"
    added = switch("s", "decision1", "{a: output1, c: output1}")
    report = validated(tmp_path / "kept", {"astra.yaml": NAMES + added, "data/input1.csv": ""})
    assert found(report) == []


@pytest.mark.parametrize(
    "added, expected",
    [
        (
            switch("s", "decision1", "{a: out}") + output("out", "[s]"),
            ["/outputs/out/inputs/0", "/outputs/s/cases/a"],
        ),
        (
            switch("t1", "decision1", "{a: t2, b: output1}") + switch("t2", "decision1", "{a: t1}"),
            ["/outputs/t1/cases/a", "/outputs/t2/cases/a"],
        ),
        (
            switch("s", "decision1", "{c: out}") + output("out", "[s]"),
            ["/outputs/out/inputs/0", "/outputs/s/cases/c"],
        ),
    ],
    ids=["an-output-and-a-switch", "two-switches", "a-case-on-an-excluded-option"],
)
def test_a_case_on_a_cycle_breaks_output_cycle(
    tmp_path: Path, added: str, expected: list[str]
) -> None:
    """Rules, `OUTPUT_CYCLE`: no output reads itself through `inputs` and `cases`, a case taken
    or not, on an excluded option too. It is reported at each entry and case on the cycle."""
    report = validated(tmp_path, {"astra.yaml": NAMES + added, "data/input1.csv": "1\n"})
    assert found(report) == ordered(
        ("OUTPUT_CYCLE", "astra.yaml", pointer, None) for pointer in expected
    )


def test_an_output_reading_a_switch_that_doesnt_read_it_keeps_output_cycle(tmp_path: Path) -> None:
    added = switch("s", "decision1", "{a: output1}") + output("out", "[s]")
    report = validated(tmp_path, {"astra.yaml": NAMES + added, "data/input1.csv": "1\n"})
    assert found(report) == []


# --- UNUSED_DECISION and INACTIVE_DECISION ---

UNUSED = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
  decision2:
    options: {a: {}, b: {}}
  decision3:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  gate:
    switch: decision1
    cases: {b: output1}
  output4:
    type: figure
    format: png
    inputs: [gate]
    decisions: [decision3]
    recipe:
      command: python make.py '{inputs.gate}' '{decisions.decision3}' '{output}'
universes:
  u1:
    decisions: {decision1: a, decision2: a, decision3: a}
"""
"""`u1` sets `decision2`, which nothing lists or switches on, and `decision3`, which `output4`
lists, where `gate` takes nothing, so `output4` isn't built in `u1`."""


def test_a_key_no_branch_uses_is_an_error_and_one_this_universe_doesnt_use_a_warning(
    tmp_path: Path,
) -> None:
    """Rules: a universe's own `decisions` set only decisions it uses on some branch
    (`UNUSED_DECISION`, MUST), and, of those, only decisions it uses (`INACTIVE_DECISION`,
    SHOULD). Results *uses on some branch*: `output4` lists `decision3`, whatever case `gate`
    takes; nothing lists `decision2`. Both are reported at the universe's `decisions`, keyed
    by the key."""
    report = validated(tmp_path, {"astra.yaml": UNUSED})
    assert found(report) == [
        ("INACTIVE_DECISION", "astra.yaml", "/universes/u1/decisions", "decision3"),
        ("UNUSED_DECISION", "astra.yaml", "/universes/u1/decisions", "decision2"),
    ]
    levels = {d.code: d.level for d in report.diagnostics}
    assert levels == {"INACTIVE_DECISION": "warning", "UNUSED_DECISION": "error"}
    messages = {d.code: d.message for d in report.diagnostics}
    assert "no branch" in messages["UNUSED_DECISION"]
    assert "doesn't use" in messages["INACTIVE_DECISION"]
    assert not report.valid


def test_keys_a_universe_uses_keep_both_rules(tmp_path: Path) -> None:
    """Results *uses*: where `decision1` selects `b`, `gate` takes `output1`, `output4` is built
    and planned, and `u1` uses both its keys."""
    text = variant(
        UNUSED, ("{decision1: a, decision2: a, decision3: a}", "{decision1: b, decision3: a}")
    )
    assert found(validated(tmp_path, {"astra.yaml": text})) == []


BASE_UNIVERSE = """\
spec_version: "0.1.0"
decisions:
  d:
    options: {a: {}, b: {}}
  e:
    options: {p: {}, q: {}}
outputs:
  x:
    type: metric
    format: json
    decisions: [d, e]
    recipe:
      command: python make.py '{decisions.d}' '{decisions.e}' '{output}'
  sw:
    switch: e
    cases: {p: x, q: x}
  cmp:
    type: table
    format: csv
    inputs: [sw#u2, sw#u3]
    recipe:
      command: python make.py {inputs} '{output}'
universes:
  u1:
    decisions: {d: a}
  u2:
    derived_from: u1
    decisions: {e: p}
  u3:
    derived_from: u1
    decisions: {e: q}
"""
"""`cmp`, built once, reads `sw` pinned to `u2` and `u3`, which derive from `u1` and inherit its
`d`; nothing is reached in `u1` itself."""


def test_a_base_universes_key_used_only_where_it_is_inherited_is_inactive(
    tmp_path: Path,
) -> None:
    """Results *uses on some branch*: a universe uses a decision on some branch where a universe
    inheriting its key for it, without setting it, does. `u1` doesn't use `d`, so its key is
    `INACTIVE_DECISION`, not `UNUSED_DECISION`."""
    report = validated(tmp_path, {"astra.yaml": BASE_UNIVERSE})
    assert found(report) == [("INACTIVE_DECISION", "astra.yaml", "/universes/u1/decisions", "d")]
    assert report.valid


EXCLUDED_CASE = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options:
      a: {}
      b: {}
      c:
        excluded: It isn't what this analysis is for.
  decision9:
    options: {p: {}, q: {}}
outputs:
  o_a:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  o_c:
    type: metric
    format: json
    decisions: [decision9]
    recipe:
      command: python make.py '{decisions.decision9}' '{output}'
  sw:
    switch: decision1
    cases: {a: o_a, c: o_c}
universes:
  u1:
    decisions: {decision1: a, decision9: p}
"""


def test_a_case_on_an_excluded_option_is_a_branch(tmp_path: Path) -> None:
    """Results *uses on some branch*: every case of every switch is followed, one on an excluded
    option too, though it is never taken. `decision9`, listed only through it, is used on some
    branch, so `u1`'s key is `INACTIVE_DECISION` alone."""
    report = validated(tmp_path, {"astra.yaml": EXCLUDED_CASE})
    assert found(report) == [
        ("INACTIVE_DECISION", "astra.yaml", "/universes/u1/decisions", "decision9")
    ]


def test_a_universe_with_no_effective_selection_is_judged_for_keys_no_branch_uses(
    tmp_path: Path,
) -> None:
    """`u9` has no effective selection, so what it takes and uses is undetermined, and
    `INACTIVE_DECISION` isn't judged on `decision3`; whether a key is used on some branch
    doesn't depend on the selection, so `UNUSED_DECISION` is, on `decision2`."""
    text = variant(
        UNUSED,
        ("{decision1: a, decision2: a, decision3: a}", "{decision1: b, decision3: a}"),
    ) + ("  u9:\n    derived_from: nowhere\n    decisions: {decision2: a, decision3: a}\n")
    assert found(validated(tmp_path, {"astra.yaml": text})) == [
        ("UNKNOWN_DERIVED_FROM", "astra.yaml", "/universes/u9/derived_from", None),
        ("UNUSED_DECISION", "astra.yaml", "/universes/u9/decisions", "decision2"),
    ]


def test_an_address_that_names_nothing_leaves_every_key_unjudged(tmp_path: Path) -> None:
    """What a branch through a case that names nothing would use is unknown, so no key of the
    analysis's universes is judged `UNUSED_DECISION`; the case is reported, and nothing else.
    Where the case names `output1`, `decision2` is."""
    text = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
  decision2:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  sw:
    switch: decision1
    cases: {a: nothing, b: output1}
universes:
  u1:
    decisions: {decision1: b, decision2: a}
"""
    assert found(validated(tmp_path / "blind", {"astra.yaml": text})) == [
        ("UNRESOLVED_ADDRESS", "astra.yaml", "/outputs/sw/cases/a", None)
    ]
    text = variant(text, ("{a: nothing, b: output1}", "{a: output1, b: output1}"))
    assert found(validated(tmp_path / "seen", {"astra.yaml": text})) == [
        ("UNUSED_DECISION", "astra.yaml", "/universes/u1/decisions", "decision2")
    ]


# --- what a universe uses ---


def test_the_running_example_breaks_no_rule(running: Path) -> None:
    """Elements and Results: `u1` uses `decision1`, `decision3` and `stage.decision2`; `u2`
    uses `decision1`, as `switch1` is reached there, and `stage.decision2`, and inherits
    `decision3`, which it doesn't use, without a diagnostic."""
    assert found(api.validate(running)) == []


def test_a_universe_setting_a_decision_it_uses_only_on_another_branch_is_warned(
    tmp_path: Path,
) -> None:
    """Results *uses*: `output6` isn't built in `u2`, so `u2` doesn't use `decision3`; set there
    itself, it is `INACTIVE_DECISION`, a warning."""
    root = variant(
        RUNNING, ("decisions: {decision1: a}", "decisions: {decision1: a, decision3: a}")
    )
    report = validated(tmp_path, {**RUNNING_FILES, "astra.yaml": root})
    assert found(report) == [
        ("INACTIVE_DECISION", "astra.yaml", "/universes/u2/decisions", "decision3")
    ]
    assert report.valid


GATED = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  gate:
    switch: decision1
    cases: {b: output1}
  output4:
    type: figure
    format: png
    inputs: [gate]
    recipe:
      command: python make.py '{inputs.gate}' '{output}'
universes:
  u1:
    decisions: {decision1: b}
  u2: {}
"""
"""`decision1` turns `output4` off where it selects `a`; `u2` sets nothing."""


def test_the_decision_that_turns_an_output_off_is_used(tmp_path: Path) -> None:
    """Results *uses*: a universe uses the decision each switch reached in it switches on,
    whatever it takes, so `u2`, where `gate` is reached, must set `decision1`
    (`MISSING_DECISION`), though nothing planned lists it."""
    report = validated(tmp_path, {"astra.yaml": GATED})
    assert found(report) == [("MISSING_DECISION", "astra.yaml", "/universes/u2", None)]
    (diagnostic,) = report.diagnostics
    assert "selects nothing for `decision1`" in diagnostic.message


def test_a_decision_nothing_uses_needs_no_key(tmp_path: Path) -> None:
    """Rules, `MISSING_DECISION`: an effective selection sets every decision its universe uses;
    `decision2`, which nothing lists or switches on, needn't be set."""
    text = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options:
      a: {}
      b: {}
  decision2:
    options:
      a: {}
      b: {}
outputs:
  output1:
    type: metric
    format: json
    decisions: [decision1]
    recipe:
      command: python make.py '{decisions.decision1}' '{output}'
universes:
  u1:
    decisions: {decision1: a}
"""
    assert found(validated(tmp_path, {"astra.yaml": text})) == []


# --- driving an analysis whose decisions nothing uses ---

DRIVING_TOOLS = """\
spec_version: "0.1.0"
analyses:
  tools: {path: tools}
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  result:
    type: metric
    format: json
    inputs: [tools.output10]
    decisions: [decision1]
    recipe:
      command: python make.py '{inputs.tools.output10}' '{decisions.decision1}' '{output}'
universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: b}
"""

TOOLS_WITH_A_DECISION = """\
spec_version: "0.1.0"
analyses:
  parent: {path: ..}
inputs:
  input3: {path: data/input3.csv}
decisions:
  decision7:
    options: {x: {}, y: {}}
outputs:
  output9:
    type: data
    format: csv
    inputs: [input3]
    decisions: [decision7]
    recipe:
      command: python make.py '{inputs.input3}' '{decisions.decision7}' '{output}'
  output10:
    type: metric
    format: json
    decisions: [parent.decision1]
    recipe:
      command: python make.py '{decisions.parent.decision1}' '{output}'
"""
"""Elements' `tools`, with a decision that only `output9` lists."""


def test_an_analysis_none_of_whose_decisions_is_used_is_driven_without_a_key(
    tmp_path: Path,
) -> None:
    """Elements: an analysis with no decisions of its own, or none that a universe of the
    driving analysis uses, has nothing to set. The root reads `tools.output10`, built per
    universe, and nothing of `output9`, so no key drives `tools`, and it is built in `u1` and
    `u2`."""
    files = {
        "astra.yaml": DRIVING_TOOLS,
        "tools/astra.yaml": TOOLS_WITH_A_DECISION,
        "tools/data/input3.csv": "3\n",
    }
    assert found(validated(tmp_path, files)) == []


def test_an_analysis_one_of_whose_decisions_is_used_is_driven_only_by_a_key(
    tmp_path: Path,
) -> None:
    """Rules, `NOT_BUILT_IN_UNIVERSE` and `UNDRIVEN_DECLARATION`: read too, `output9` makes the
    root's universes use `tools.decision7`, so `tools` needs a key, and both reads break both
    rules; `MISSING_DECISION` is judged only for the analyses the universes drive."""
    root = variant(DRIVING_TOOLS, ("[tools.output10]", "[tools.output10, tools.output9]"))
    files = {
        "astra.yaml": root,
        "tools/astra.yaml": TOOLS_WITH_A_DECISION,
        "tools/data/input3.csv": "3\n",
    }
    assert found(validated(tmp_path, files)) == ordered(
        (code, "astra.yaml", f"/outputs/result/inputs/{index}", None)
        for code in ("NOT_BUILT_IN_UNIVERSE", "UNDRIVEN_DECLARATION")
        for index in (0, 1)
    )


# --- constraints, among the decisions used ---

CONSTRAINED = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options:
      a: {}
      b:
        requires: [decision3.b]
        incompatible_with: [decision2.b]
  decision2:
    options:
      a:
        requires: [decision1.a]
      b: {}
  decision3:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    decisions: [decision1]
    recipe:
      command: python make.py '{decisions.decision1}' '{output}'
  detail:
    type: metric
    format: json
    decisions: [decision2]
    recipe:
      command: python make.py '{decisions.decision2}' '{output}'
  gate:
    switch: decision1
    cases: {a: detail}
universes:
  u1:
    decisions: {decision1: a, decision2: a}
  u2:
    decisions: {decision1: b, decision2: b}
  u3:
    decisions: {decision1: b, decision2: a}
"""
"""`decision2` is used only where `gate` takes `detail`, in `u1`; nothing uses `decision3`."""


def test_constraints_hold_among_the_decisions_a_universe_uses(tmp_path: Path) -> None:
    """Results: constraints hold among the decisions a universe uses; one outside these counts
    as selecting nothing. In `u2` and `u3`, `decision2` isn't used: `decision1.b`'s
    `incompatible_with` naming it holds, and its own `requires` isn't judged; `decision1.b`'s
    `requires` naming the unused `decision3` fails (`MISSING_REQUIRED_OPTION`)."""
    report = validated(tmp_path, {"astra.yaml": CONSTRAINED})
    assert found(report) == ordered(
        [
            ("MISSING_REQUIRED_OPTION", "astra.yaml", "/universes/u2/decisions", "decision1"),
            ("INACTIVE_DECISION", "astra.yaml", "/universes/u2/decisions", "decision2"),
            ("MISSING_REQUIRED_OPTION", "astra.yaml", "/universes/u3/decisions", "decision1"),
            ("INACTIVE_DECISION", "astra.yaml", "/universes/u3/decisions", "decision2"),
        ]
    )


def test_constraints_on_a_decision_used_are_judged(tmp_path: Path) -> None:
    """Rules, `MISSING_REQUIRED_OPTION` and `INCOMPATIBLE_OPTIONS`: where `gate` takes `detail`
    for both options, every universe uses `decision2`, and its constraints are judged."""
    text = variant(CONSTRAINED, ("cases: {a: detail}", "cases: {a: detail, b: detail}"))
    assert found(validated(tmp_path, {"astra.yaml": text})) == ordered(
        [
            ("MISSING_REQUIRED_OPTION", "astra.yaml", "/universes/u2/decisions", "decision1"),
            ("INCOMPATIBLE_OPTIONS", "astra.yaml", "/universes/u2/decisions", "decision1"),
            ("MISSING_REQUIRED_OPTION", "astra.yaml", "/universes/u3/decisions", "decision1"),
            ("MISSING_REQUIRED_OPTION", "astra.yaml", "/universes/u3/decisions", "decision2"),
        ]
    )


PINNING_STAGE = """\
spec_version: "0.1.0"
analyses:
  stage: {path: stage}
outputs:
  out:
    type: table
    format: csv
    inputs: [stage.output3#v1]
    recipe:
      command: python make.py '{inputs.stage.output3#v1}' '{output}'
"""

MODED_STAGE = """\
spec_version: "0.1.0"
decisions:
  mode:
    options: {x: {}, y: {}}
  decision2:
    options:
      a:
        requires: [mode.x]
      b: {}
outputs:
  output3:
    type: data
    format: csv
    decisions: [decision2]
    recipe:
      command: python make.py '{decisions.decision2}' '{output}'
  plain:
    type: data
    format: csv
    recipe:
      command: python make.py '{output}'
  sel:
    switch: mode
    cases: {x: output3, y: plain}
universes:
  v1:
    decisions: {mode: y, decision2: a}
"""
"""`stage`'s own `v1` takes `plain`, so `stage` driving uses `mode` there, and not
`decision2`."""


def test_constraints_hold_among_the_decisions_used_through_a_pin(tmp_path: Path) -> None:
    """Results: in another analysis's universe, constraints hold too among the decisions that
    something reached through a pin uses there. The root pins `stage.output3` to `v1`, so
    `decision2: a` there must meet its `requires` (`MISSING_REQUIRED_OPTION`), reported in
    `stage`'s file; `stage`'s own run doesn't use `decision2` in `v1` (`INACTIVE_DECISION`)."""
    files = {"astra.yaml": PINNING_STAGE, "stage/astra.yaml": MODED_STAGE}
    assert found(validated(tmp_path / "pinned", files)) == ordered(
        [
            ("INACTIVE_DECISION", "stage/astra.yaml", "/universes/v1/decisions", "decision2"),
            ("MISSING_REQUIRED_OPTION", "stage/astra.yaml", "/universes/v1/decisions", "decision2"),
        ]
    )
    files["astra.yaml"] = PINNING_STAGE.replace("stage.output3#v1", "stage.plain#v1")
    assert found(validated(tmp_path / "plain", files)) == [
        ("INACTIVE_DECISION", "stage/astra.yaml", "/universes/v1/decisions", "decision2")
    ]


def test_a_constraint_is_no_use(tmp_path: Path) -> None:
    """Rules: constraints never make a decision used, nor need its analysis driven. The root
    reads `other.output1` though no key drives `other` (`NOT_BUILT_IN_UNIVERSE`,
    `UNDRIVEN_DECLARATION`); the `requires` naming `other.decision1` isn't met, as nothing sets
    it (`MISSING_REQUIRED_OPTION`), and isn't itself judged as a use."""
    root = """\
spec_version: "0.1.0"
analyses:
  other: {path: other}
decisions:
  decision1:
    options:
      a:
        requires: [other.decision1.a]
      b: {}
outputs:
  result:
    type: metric
    format: json
    inputs: [other.output1]
    decisions: [decision1]
    recipe:
      command: python make.py '{inputs.other.output1}' '{decisions.decision1}' '{output}'
universes:
  u1:
    decisions: {decision1: a}
"""
    other = (
        'spec_version: "0.1.0"\ndecisions:\n  decision1:\n    options: {a: {}, b: {}}\n'
        "outputs:\n" + output("output1", decisions="[decision1]")
    )
    assert found(validated(tmp_path, {"astra.yaml": root, "other/astra.yaml": other})) == ordered(
        [
            ("MISSING_REQUIRED_OPTION", "astra.yaml", "/universes/u1/decisions", "decision1"),
            ("NOT_BUILT_IN_UNIVERSE", "astra.yaml", "/outputs/result/inputs/0", None),
            ("UNDRIVEN_DECLARATION", "astra.yaml", "/outputs/result/inputs/0", None),
        ]
    )


# --- PIN_NOT_BUILT ---

PINNED = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  gate:
    switch: decision1
    cases: {b: output1}
  output2:
    type: table
    format: csv
    inputs: [gate#u1]
    recipe:
      command: python make.py '{inputs.gate#u1}' '{output}'
  relay:
    switch: decision1
    cases: {a: gate#u1, b: output1}
universes:
  u1:
    decisions: {decision1: a}
  u2:
    decisions: {decision1: b}
findings:
  finding1:
    claim: The gate is cited where it is pinned.
    evidence:
      - artifact: gate#u1
"""
"""`gate` is pinned to `u1`, where it has no case for `decision1`'s `a`, by an `inputs` entry,
a case and an `artifact`."""


def test_a_pin_to_a_universe_where_its_target_isnt_built_breaks_pin_not_built(
    tmp_path: Path,
) -> None:
    """Rules, `PIN_NOT_BUILT`: every pinned output, a switch too, is built in the universe it is
    pinned to; pins in `inputs`, in `cases` and in `artifact`. Each is reported at the pin, and
    says which switch has no case there."""
    report = validated(tmp_path, {"astra.yaml": PINNED})
    assert found(report) == ordered(
        ("PIN_NOT_BUILT", "astra.yaml", pointer, None)
        for pointer in (
            "/outputs/output2/inputs/0",
            "/outputs/relay/cases/a",
            "/findings/finding1/evidence/0/artifact",
        )
    )
    for diagnostic in report.diagnostics:
        assert diagnostic.level == "error"
        assert "isn't built" in diagnostic.message
        assert "has no case" in diagnostic.message


def test_a_pin_to_a_universe_where_its_target_is_built_keeps_pin_not_built(tmp_path: Path) -> None:
    text = PINNED.replace("gate#u1", "gate#u2")
    assert found(validated(tmp_path, {"astra.yaml": text})) == []


def test_a_pin_to_an_undetermined_switch_is_reported_by_its_cause(tmp_path: Path) -> None:
    """`u3` leaves `gate`'s decision unset, so whether `gate` is built there is undetermined,
    and `PIN_NOT_BUILT` isn't judged; the pin reaches `gate` in `u3`, which so uses
    `decision1`: `MISSING_DECISION`."""
    text = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  gate:
    switch: decision1
    cases: {b: output1}
  output2:
    type: table
    format: csv
    inputs: [gate#u3]
    recipe:
      command: python make.py '{inputs.gate#u3}' '{output}'
universes:
  u3: {}
"""
    assert found(validated(tmp_path, {"astra.yaml": text})) == [
        ("MISSING_DECISION", "astra.yaml", "/universes/u3", None)
    ]


SUB2 = """\
spec_version: "0.1.0"
decisions:
  decision0:
    options: {x: {}, y: {}}
  decision5:
    options: {p: {}, q: {}}
outputs:
  fit:
    type: metric
    format: json
    decisions: [decision5]
    recipe:
      command: python make.py '{decisions.decision5}' '{output}'
  other:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  sw:
    switch: decision0
    cases: {x: fit, y: other}
universes:
  w1:
    decisions: {decision0: y}
"""
"""An analysis whose own `w1` takes `other`, and so neither uses nor may set `decision5`."""


def test_a_pin_no_reach_follows_asks_its_universe_for_nothing(tmp_path: Path) -> None:
    """Rules, `PIN_NOT_BUILT`: the second row is judged for a pin the driving analysis reaches.
    The root reads nothing of `sub`, so `sub`'s pin of `sub2.fit` to `w1` asks `w1` for nothing,
    though `fit` lists `decision5`, which `w1` doesn't set."""
    sub = """\
spec_version: "0.1.0"
analyses:
  sub2: {path: sub2}
outputs:
  o_unread:
    type: metric
    format: json
    inputs: [sub2.fit#w1]
    recipe:
      command: python make.py '{inputs.sub2.fit#w1}' '{output}'
"""
    root = MINIMAL + "analyses:\n  sub: {path: sub}\n"
    files = {"astra.yaml": root, "sub/astra.yaml": sub, "sub/sub2/astra.yaml": SUB2}
    assert found(validated(tmp_path, files)) == []


def test_a_reached_pin_asks_its_universe_for_what_it_reaches_uses_there(tmp_path: Path) -> None:
    """Rules, `PIN_NOT_BUILT`: a universe of another analysis, named by a reached pin, sets each
    decision that something reached through the pin uses there and the universe doesn't. The
    pin reaches `report` in `v1`, which reads `sw1`, which switches on `decision1`; `sub`'s own
    run takes `other` in `v1`, and doesn't use it. Reported at the pin, in the root's file."""
    root = """\
spec_version: "0.1.0"
analyses:
  sub: {path: sub}
outputs:
  result:
    type: metric
    format: json
    inputs: [sub.report#v1]
    recipe:
      command: python make.py '{inputs.sub.report#v1}' '{output}'
universes:
  u1: {}
"""
    sub = (
        """\
spec_version: "0.1.0"
decisions:
  decision0:
    options: {x: {}, y: {}}
  decision1:
    options: {a: {}, b: {}}
outputs:
"""
        + output("o_x")
        + output("o_y")
        + output("other")
        + output("report", "[sw1]")
        + switch("sw1", "decision1", "{a: o_x, b: o_y}")
        + switch("sw", "decision0", "{x: report, y: other}")
        + "universes:\n  v1:\n    decisions: {decision0: y}\n"
    )
    report = validated(tmp_path, {"astra.yaml": root, "sub/astra.yaml": sub})
    assert found(report) == [("PIN_NOT_BUILT", "astra.yaml", "/outputs/result/inputs/0", None)]
    (diagnostic,) = report.diagnostics
    assert "neither sets nor uses" in diagnostic.message


def test_a_decision_a_pinned_universe_uses_itself_is_missing_there(tmp_path: Path) -> None:
    """Rules, `PIN_NOT_BUILT`, second row: what the universe uses itself is left to
    `MISSING_DECISION`, reported in its own file. `subanalysis` plans `output1` in `v1`, which
    uses `decision1`."""
    root = """\
spec_version: "0.1.0"
analyses:
  subanalysis: {path: subanalysis}
outputs:
  result:
    type: metric
    format: json
    inputs: [subanalysis.output1#v1]
    recipe:
      command: python make.py '{inputs.subanalysis.output1#v1}' '{output}'
"""
    sub = MINIMAL.replace("result:", "output1:").replace(
        "    recipe:", "    decisions: [decision1]\n    recipe:"
    ) + ("decisions:\n  decision1:\n    options: {a: {}, b: {}}\nuniverses:\n  v1: {}\n")
    files = {"astra.yaml": root, "subanalysis/astra.yaml": sub}
    assert found(validated(tmp_path, files)) == [
        ("MISSING_DECISION", "subanalysis/astra.yaml", "/universes/v1", None)
    ]


def test_a_pin_needing_a_key_its_universe_may_not_set_has_no_valid_form(tmp_path: Path) -> None:
    """Elements: a pin into an analysis's own universe can read only what uses decisions that
    universe uses on some branch, as it may set no other. Through the import `stage_v1`, the
    root pins `stage.inner.output8` to `stage`'s `v1`; nothing of `stage` reads `inner`. Without
    a key for `inner.decision4`, `PIN_NOT_BUILT`, at the pin; with it, `UNUSED_DECISION` in
    `stage`'s file."""
    root = """\
spec_version: "0.1.0"
analyses:
  stage: {path: stage}
outputs:
  result:
    type: metric
    format: json
    inputs: [stage.inner.output8#stage_v1]
    recipe:
      command: python make.py '{inputs.stage.inner.output8#stage_v1}' '{output}'
universes:
  stage_v1: {analysis: stage, universe: v1}
"""
    stage = """\
spec_version: "0.1.0"
analyses:
  inner: {path: inner}
decisions:
  decision2:
    options: {a: {}, b: {}}
outputs:
  output3:
    type: data
    format: csv
    decisions: [decision2]
    recipe:
      command: python make.py '{decisions.decision2}' '{output}'
universes:
  v1:
    decisions: {decision2: a}
"""
    inner = (
        'spec_version: "0.1.0"\n'
        "decisions:\n  decision4:\n    options: {a: {}, b: {}}\n"
        "outputs:\n" + output("output8", decisions="[decision4]")
    )
    files = {"astra.yaml": root, "stage/astra.yaml": stage, "stage/inner/astra.yaml": inner}
    assert found(validated(tmp_path / "unset", files)) == [
        ("PIN_NOT_BUILT", "astra.yaml", "/outputs/result/inputs/0", None)
    ]
    files["stage/astra.yaml"] = stage.replace(
        "{decision2: a}", "{decision2: a, inner.decision4: a}"
    )
    assert found(validated(tmp_path / "set", files)) == [
        ("UNUSED_DECISION", "stage/astra.yaml", "/universes/v1/decisions", "inner.decision4")
    ]


# --- driving, through switches ---

STAGE_SWITCH = (
    """\
spec_version: "0.1.0"
decisions:
  decision2:
    options: {a: {}, b: {}}
outputs:
"""
    + output("output3")
    + output("output4")
    + switch("switch3", "decision2", "{a: output3, b: output4}")
)
"""A `stage` whose `switch3` switches on its own `decision2`, and which has no universes."""


def test_another_analysiss_switch_read_through_an_undriven_chain(tmp_path: Path) -> None:
    """Rules, `NOT_BUILT_IN_UNIVERSE` and `UNDRIVEN_DECLARATION`: reading another analysis's
    switch needs that analysis built where it reads, whatever case the switch takes, so both
    are reported at `stage.switch3` in the root's file, though `switch3` is undetermined in
    `u1`; `MISSING_DECISION` isn't, as no key drives `stage`. With a key, nothing is."""
    root = (
        'spec_version: "0.1.0"\nanalyses:\n  stage: {path: stage}\n'
        "decisions:\n  decision1:\n    options: {a: {}, b: {}}\n"
        "outputs:\n"
        + output("output1", "[stage.switch3]", "[decision1]")
        + "universes:\n  u1:\n    decisions: {decision1: a}\n"
    )
    files = {"astra.yaml": root, "stage/astra.yaml": STAGE_SWITCH}
    assert found(validated(tmp_path / "undriven", files)) == ordered(
        (code, "astra.yaml", "/outputs/output1/inputs/0", None)
        for code in ("NOT_BUILT_IN_UNIVERSE", "UNDRIVEN_DECLARATION")
    )
    files["astra.yaml"] = root.replace("{decision1: a}", "{decision1: a, stage.decision2: a}")
    assert found(validated(tmp_path / "driven", files)) == []


def test_a_switch_on_an_undriven_analysiss_decision(tmp_path: Path) -> None:
    """Rules: a switch uses the decision it switches on. The root's own `s` switches on
    `stage.decision2`, and no key drives `stage`: both rules are reported at its `switch`,
    though `s` is undetermined."""
    root = (
        'spec_version: "0.1.0"\nanalyses:\n  stage: {path: stage}\n'
        "decisions:\n  decision1:\n    options: {a: {}, b: {}}\n"
        "outputs:\n"
        + output("result", decisions="[decision1]")
        + output("output1")
        + switch("s", "stage.decision2", "{a: output1}")
        + "universes:\n  u1:\n    decisions: {decision1: a}\n"
    )
    files = {"astra.yaml": root, "stage/astra.yaml": STAGE_SWITCH}
    assert found(validated(tmp_path, files)) == ordered(
        (code, "astra.yaml", "/outputs/s/switch", None)
        for code in ("NOT_BUILT_IN_UNIVERSE", "UNDRIVEN_DECLARATION")
    )


def test_a_driven_analysiss_switch_on_an_undriven_analysiss_decision(tmp_path: Path) -> None:
    """Rules: `NOT_BUILT_IN_UNIVERSE` is reported in the file that holds the address, and
    `UNDRIVEN_DECLARATION` only in the file of the universe's analysis. `u1` drives `stage`,
    whose `sw` switches on `other.decision1`, and nothing drives `other`."""
    root = (
        'spec_version: "0.1.0"\nanalyses:\n  stage: {path: stage}\n'
        "outputs:\n"
        + output("result", "[stage.output3]")
        + "universes:\n  u1:\n    decisions: {stage.decision2: a}\n"
    )
    stage = (
        'spec_version: "0.1.0"\nanalyses:\n  other: {path: ../other}\n'
        "decisions:\n  decision2:\n    options: {a: {}, b: {}}\n"
        "outputs:\n"
        + output("oa")
        + output("ob")
        + switch("sw", "other.decision1", "{a: oa, b: ob}")
        + output("output3", "[sw]", "[decision2]")
    )
    other = (
        'spec_version: "0.1.0"\ndecisions:\n  decision1:\n    options: {a: {}, b: {}}\n'
        "outputs:\n" + output("output1", decisions="[decision1]")
    )
    files = {"astra.yaml": root, "stage/astra.yaml": stage, "other/astra.yaml": other}
    assert found(validated(tmp_path, files)) == [
        ("NOT_BUILT_IN_UNIVERSE", "stage/astra.yaml", "/outputs/sw/switch", None)
    ]


UNDETERMINED = (
    'spec_version: "0.1.0"\nanalyses:\n  stage: {path: stage}\n'
    "decisions:\n  decision1:\n    options: {a: {}, b: {}}\n"
    "outputs:\n"
    + output("result", "[sw]")
    + switch("sw", "decision1", "{a: stage.o1}")
    + "universes:\n  u1:\n    decisions: {decision1: a}\n  u2: {}\n"
)
"""`sw` takes `stage.o1` in `u1` and is undetermined in `u2`, which sets nothing."""

O1_STAGE = (
    'spec_version: "0.1.0"\ndecisions:\n  decision2:\n    options: {a: {}, b: {}}\n'
    "outputs:\n" + output("o1", decisions="[decision2]")
)


def test_driving_one_universe_determines_is_judged_there(tmp_path: Path) -> None:
    """`u1` definitely uses `stage.decision2`, so `stage`, which no key drives, is undriven, and
    `u1`'s read of `stage.o1` breaks both rules at the case; `u2` leaves `decision1` unset
    (`MISSING_DECISION`)."""
    files = {"astra.yaml": UNDETERMINED, "stage/astra.yaml": O1_STAGE}
    assert found(validated(tmp_path, files)) == ordered(
        [
            ("MISSING_DECISION", "astra.yaml", "/universes/u2", None),
            ("NOT_BUILT_IN_UNIVERSE", "astra.yaml", "/outputs/sw/cases/a", None),
            ("UNDRIVEN_DECLARATION", "astra.yaml", "/outputs/sw/cases/a", None),
        ]
    )


def test_driving_no_universe_determines_isnt_judged(tmp_path: Path) -> None:
    """With `u2` alone, whether `stage` is used, and so driven, is undetermined, and only the
    cause is reported."""
    root = variant(UNDETERMINED, ("  u1:\n    decisions: {decision1: a}\n", ""))
    files = {"astra.yaml": root, "stage/astra.yaml": O1_STAGE}
    assert found(validated(tmp_path, files)) == [
        ("MISSING_DECISION", "astra.yaml", "/universes/u2", None)
    ]


def test_evidence_citing_another_analysiss_switch_reads_it(tmp_path: Path) -> None:
    """Rules, `NOT_BUILT_IN_UNIVERSE` and `UNDRIVEN_DECLARATION`: evidence citing a switch
    without a pin reaches it in each of the root's universes, as an output's `inputs` entry
    does, so both are reported at the `artifact` where no key drives `stage`, and neither once
    `u1` sets `stage.decision2`."""
    root = (
        MINIMAL
        + "analyses:\n  stage: {path: stage}\nuniverses:\n  u1: {}\n"
        + FINDING % "stage.switch3"
    )
    files = {"astra.yaml": root, "stage/astra.yaml": STAGE_SWITCH}
    assert found(validated(tmp_path / "undriven", files)) == ordered(
        (code, "astra.yaml", "/findings/finding1/evidence/0/artifact", None)
        for code in ("NOT_BUILT_IN_UNIVERSE", "UNDRIVEN_DECLARATION")
    )
    files["astra.yaml"] = root.replace("  u1: {}\n", "  u1:\n    decisions: {stage.decision2: a}\n")
    assert found(validated(tmp_path / "driven", files)) == []


# --- a switch that chooses between declared analyses ---


def test_a_switch_between_analyses_drives_each_where_it_takes_it(tmp_path: Path) -> None:
    """Elements: a switch can choose between analyses. `q` uses and sets `fast.decision5`, `c`
    `slow.decision5`; `m` uses `method` alone, and needn't set `prior`; `tools`, none of whose
    decisions is used, is driven without a key."""
    assert found(validated(tmp_path, CHOOSING_FILES)) == []


CHOOSING_VARIANTS: Mapping[str, tuple[tuple[tuple[str, str], ...], list[Seen]]] = {
    "m-sets-prior": (
        (("{method: manual}", "{method: manual, prior: flat}"),),
        [("INACTIVE_DECISION", "astra.yaml", "/universes/m/decisions", "prior")],
    ),
    "q-sets-slow-decision5": (
        (("fast.decision5: x}", "fast.decision5: x, slow.decision5: x}"),),
        [("INACTIVE_DECISION", "astra.yaml", "/universes/q/decisions", "slow.decision5")],
    ),
    "q-sets-tools-decision6": (
        (("fast.decision5: x}", "fast.decision5: x, tools.decision6: p}"),),
        [("UNUSED_DECISION", "astra.yaml", "/universes/q/decisions", "tools.decision6")],
    ),
    "q-switches-to-careful": (
        (("{method: quick,", "{method: careful,"),),
        [
            ("MISSING_DECISION", "astra.yaml", "/universes/q/decisions", None),
            ("INACTIVE_DECISION", "astra.yaml", "/universes/q/decisions", "fast.decision5"),
        ],
    ),
    "no-key-drives-fast": (
        ((", fast.decision5: x}", "}"),),
        [
            ("NOT_BUILT_IN_UNIVERSE", "astra.yaml", "/outputs/model/cases/quick", None),
            ("UNDRIVEN_DECLARATION", "astra.yaml", "/outputs/model/cases/quick", None),
        ],
    ),
    "model-switches-on-fast-decision5-which-no-key-drives": (
        (
            ("switch: method", "switch: fast.decision5"),
            ("{quick: fast.fit, careful: slow.fit}", "{x: fast.fit, y: slow.fit}"),
            ("{method: quick, prior: flat, fast.decision5: x}", "{prior: flat}"),
            (
                "{method: careful, prior: flat, slow.decision5: y}",
                "{prior: flat, slow.decision5: y}",
            ),
            ("m: {decisions: {method: manual}}", "m: {}"),
        ),
        [
            ("NOT_BUILT_IN_UNIVERSE", "astra.yaml", "/outputs/model/switch", None),
            ("UNDRIVEN_DECLARATION", "astra.yaml", "/outputs/model/switch", None),
        ],
    ),
}
"""Each change to `CHOOSING`'s root file, and what it then breaks."""


@pytest.mark.parametrize("name", CHOOSING_VARIANTS)
def test_what_a_switch_between_analyses_breaks_once_changed(tmp_path: Path, name: str) -> None:
    """Results *uses* and *uses on some branch*, and Rules:

    - `m` setting `prior`, and `q` setting `slow.decision5`, set a decision used only on another
      branch (`INACTIVE_DECISION`);
    - `q` setting `tools.decision6` sets one no branch uses: `tools.unused` is never reached
      (`UNUSED_DECISION`);
    - `q` switching to `careful` now uses `slow.decision5`, unset (`MISSING_DECISION`), and no
      longer uses its own `fast.decision5` (`INACTIVE_DECISION`);
    - with no key for `fast`, `fast.fit` is still planned in `q`, and uses `fast.decision5`, so
      `fast` needs one: both driving rules at the case `q` takes, and no `MISSING_DECISION`;
    - `model` switching on `fast.decision5`, which no key sets, gets both at its `switch`,
      though it is undetermined in every universe."""
    edits, expected = CHOOSING_VARIANTS[name]
    files = {**CHOOSING_FILES, "astra.yaml": variant(CHOOSING, *edits)}
    assert found(validated(tmp_path, files)) == ordered(expected)


# --- a switch of an analysis read at a commit ---

LIB = """\
spec_version: "0.1.0"
decisions:
  d:
    options: {a: {}, b: {}}
outputs:
  one:
    type: metric
    format: json
    decisions: [d]
    recipe:
      command: python make.py '{decisions.d}' '{output}'
  two:
    type: metric
    format: json
    decisions: [d]
    recipe:
      command: python make.py '{decisions.d}' '{output}'
  sw:
    switch: d
    cases: {a: one}
"""

FROM_COMMIT = """\
spec_version: "0.1.0"
analyses:
  lib: {path: lib, commit: "%s"}
outputs:
  result:
    type: metric
    format: json
    inputs: [lib.sw]
    recipe:
      command: python make.py '{inputs.lib.sw}' '{output}'
universes:
  u1:
    decisions: {lib.d: a}
"""
"""A root whose `u1` drives `lib`, declared at a commit, and reads its switch."""


def test_a_switch_of_an_analysis_from_a_commit_takes_the_case_written_there(
    tmp_path: Path,
) -> None:
    """Results: a switch of an analysis declared with a `commit` is read with its files at its
    commit. There, `sw`'s case for `a` is `one`; in the working tree it has since become `two`.
    `result` reads `lib.one` in `u1`."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL, "lib/astra.yaml": LIB})
    commit = git(top, "rev-parse", "HEAD").strip()
    changed = LIB.replace("cases: {a: one}", "cases: {a: two}")
    repository(top, {"astra.yaml": FROM_COMMIT % commit, "lib/astra.yaml": changed})
    assert found(api.validate(top)) == []
    stack = api.bind(top).stack
    assert stack is not None
    lib = Identity("lib", commit)
    (entry,) = [r for r in stack.resolutions if r.field == "inputs" and r.written == "lib.sw"]
    assert entry.element == Element(lib, "switch", "sw")
    u1 = Element(ROOT, "universe", "u1")
    meaning = Context(stack, Catalogue.load()).meaning
    taken = meaning.taken(entry.element, u1)
    assert taken is not None and taken.case is not None
    assert (taken.option, taken.case.written) == ("a", "one")
    through = meaning.through(entry, u1)
    assert through is not None
    assert (through.target, through.universe) == (Element(lib, "output", "one"), u1)
