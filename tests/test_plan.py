"""The plan (design §4.6): §18's planned results, each after what it reads, with their names,
owners, places, inputs, decisions and commands; `render_command` (§11 *The command as a
template*); §17's results read through their records or run at a commit; `api.plan`, its
shape `astra-plan/1`, and `astra plan`.

The stacks are §2's worked example; astra-spec's `examples/iris_pipeline`; §16's `output5`
reading §15's `subanalysis` in three universes, where `subanalysis`'s own `v1` drives its
parent (§18), with an output of every placeholder; §9's `decision3`, in an output's
`decisions`; §18's `inner` reached through `inner` and `stage.inner`; and §17's analysis from a
commit, driven and pinned.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.cli import main
from astra.plan import Plan, render_command
from astra.stack import Identity
from tests.conftest import MINIMAL, SPEC, git, git_init, repository
from tests.test_planned import ROOT, SUBANALYSIS
from tests.test_validate import WORKED_EXAMPLE


def astra(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


def results(plan: Plan) -> list[tuple[str, str]]:
    """Each result, in the plan's order: the analysis it belongs to, and its addresses (§18)."""
    return [(str(r.owner), ", ".join(p.address for p in r.places)) for r in plan.results]


def each_after_what_it_reads(plan: Plan) -> bool:
    built: set[object] = set()
    for result in plan.results:
        for read in result.inputs:
            if read.result is not None and (read.result.output, read.result.universe) not in built:
                return False
        built.add((result.output, result.universe))
    return True


# --- §2's worked example ---


@pytest.fixture(scope="module")
def worked(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {"astra.yaml": WORKED_EXAMPLE, "data/input1.csv": "1\n"}
    return repository(tmp_path_factory.mktemp("worked"), files)


def test_the_worked_example_plans_its_three_results_at_section_18s_places(worked: Path) -> None:
    """§2 *Building* and §18: `output1` in `u1` and in `u2`, then `output2`, which reads both,
    each with its record and its bytes where §18's tree puts them."""
    plan = api.plan(worked)
    assert [
        (r.names, r.universe and r.universe.id, [(p.record, p.bytes) for p in r.places])
        for r in plan.results
    ] == [
        (("output1",), "u1", [(".astra/records/u1/output1.json", "results/u1/output1.json")]),
        (("output1",), "u2", [(".astra/records/u2/output1.json", "results/u2/output1.json")]),
        (("output2",), None, [(".astra/records/output2.json", "results/output2.csv")]),
    ]
    assert each_after_what_it_reads(plan)
    one, two, compared = plan.results
    assert [(r.owner, r.workdir, r.read_only, r.run_at) for r in plan.results] == [
        (Identity(""), "", False, None)
    ] * 3
    assert [(read.entry, read.path, read.commit, read.result) for read in one.inputs] == [
        ("input1", "data/input1.csv", None, None)
    ]
    assert (dict(one.decisions), dict(two.decisions), dict(compared.decisions)) == (
        {"decision1": "a"},
        {"decision1": "b"},
        {},
    )
    assert [(read.entry, read.path, read.result) for read in compared.inputs] == [
        ("output1#u1", "results/u1/output1.json", one),
        ("output1#u2", "results/u2/output1.json", two),
    ]


def test_the_worked_example_builds_as_section_2_says(worked: Path) -> None:
    """§2 *Building*: `{decisions.decision1}` is `a` in `u1` and `b` in `u2`, `output2` reads
    the paths of both results, and `{output}` is where each result is written."""
    assert [render_command(result, worked) for result in api.plan(worked).results] == [
        "python src/output1.py 'data/input1.csv' 'a' 'results/u1/output1.json'",
        "python src/output1.py 'data/input1.csv' 'b' 'results/u2/output1.json'",
        "python src/output2.py 'results/u1/output1.json' 'results/u2/output1.json' "
        "'results/output2.csv'",
    ]


# --- examples/iris_pipeline ---


IRIS = {
    (".", "iris_data"),
    (".", "comparison"),
    (".", "split#baseline"),
    (".", "split#mlp_svm"),
    (".", "summary#baseline"),
    (".", "summary#mlp_svm"),
    (".", "classification.accuracy#baseline"),
    (".", "classification.accuracy#mlp_svm"),
    (".", "classification.predictions#baseline"),
    (".", "classification.predictions#mlp_svm"),
    (".", "feature_extraction.features#baseline"),
    (".", "feature_extraction.features#mlp_svm"),
}
"""§18, read for `examples/iris_pipeline`: the root's outputs, `iris_data` and `comparison`
built once and the others in each of its universes; what `summary` and `comparison` read,
`classification`'s `accuracy` and, through it, `predictions`, in each universe; and what
`predictions` reads, `feature_extraction`'s `features` and the root's own `split`. The root's
universes drive both stages, so each result built in them is the root's, named through the
one driven declaration to its analysis: `classification.feature_extraction` and the stages'
`iris: {path: ..}` aren't driven and add no name. `iris_data` is read by `split` and, as
`iris.iris_data`, by `features`; `feature_plot`, which nothing reads, isn't planned."""


def test_iris_pipeline_plans_with_the_names_and_owners_of_section_18(tmp_path: Path) -> None:
    shutil.copytree(SPEC / "examples" / "iris_pipeline", tmp_path / "pipeline")
    plan = api.plan(repository(tmp_path / "pipeline", {}))
    assert len(plan.results) == len(IRIS)
    assert set(results(plan)) == IRIS
    assert each_after_what_it_reads(plan)
    by_address = {result.places[0].address: result for result in plan.results}
    features = by_address["feature_extraction.features#mlp_svm"]
    assert (features.workdir, features.places[0].bytes) == (
        "feature_extraction",
        "results/mlp_svm/feature_extraction.features.npy",
    )
    assert dict(features.decisions) == {
        "method": "mlp_encoder",
        "n_components": "two",
        "iris.random_seed": "seed_42",
    }
    predictions = by_address["classification.predictions#mlp_svm"]
    assert [(read.entry, read.path) for read in predictions.inputs] == [
        ("feature_extraction.features", "results/mlp_svm/feature_extraction.features.npy"),
        ("iris.split", "results/mlp_svm/split.json"),
    ]
    assert predictions.inputs[1].result is by_address["split#mlp_svm"]


# --- §16's output5, §18's parent.output1, and §11's placeholders ---


PLACEHOLDERS = """\
  output3:
    type: table
    format: csv
    inputs: [input1, subanalysis.output1, output1#u1]
    decisions: [subanalysis.decision1]
    recipe:
      command: >-
        python make.py {{x}} '{inputs.input1}' '{inputs.subanalysis.output1}'
        '{inputs.output1#u1}' '{decisions.subanalysis.decision1}' {inputs} '{output}' }}
"""
"""An output of every placeholder of §11's table, the entries with dots and `#`, `{{` and
`}}`."""

ON_REQUEST = """\
  cond:
    type: figure
    format: png
    when: [decision1.b]
    recipe:
      command: python src/cond.py '{output}'
  reader:
    type: metric
    format: json
    inputs: [cond]
    recipe:
      command: python src/reader.py '{inputs.cond}' '{output}'
"""
"""Two outputs of `subanalysis` that nothing reads: one active only where `decision1.b` is
selected, and one that reads it without a pin and is active everywhere."""


@pytest.fixture(scope="module")
def pinning(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {
        "astra.yaml": ROOT.replace("universes:\n", PLACEHOLDERS + "universes:\n", 1),
        "data/input1.csv": "1\n",
        "subanalysis/astra.yaml": SUBANALYSIS.replace("universes:\n", ON_REQUEST + "universes:\n"),
        "subanalysis/data/input1.csv": "2\n",
    }
    return repository(tmp_path_factory.mktemp("pinning"), files)


def test_output5s_three_pins_read_three_results_each_in_its_owners_folder(pinning: Path) -> None:
    """§16 *Pins and imported universes* and §18: `subanalysis.output1#u1` reads the root's
    result, named `subanalysis.output1`; `#subanalysis_u1` and `#v1` read `subanalysis`'s own,
    in its folder under its universes' own ids; `output1#subanalysis_v1` reads the root's
    `output1` as `subanalysis`'s `v1` builds it, through `parent: {path: ..}`, named
    `parent.output1` there, which runs in the root's folder (§11)."""
    plan = api.plan(pinning)
    assert set(results(plan)) == {
        (".", "output1#u1"),
        (".", "output1#u2"),
        (".", "output3#u1"),
        (".", "output3#u2"),
        (".", "output4#u2"),
        (".", "output5"),
        (".", "subanalysis.output1#u1"),
        (".", "subanalysis.output1#u2"),
        ("subanalysis", "output1#u1"),
        ("subanalysis", "output1#v1"),
        ("subanalysis", "parent.output1#v1"),
    }
    assert each_after_what_it_reads(plan)
    (output5,) = [result for result in plan.results if result.names == ("output5",)]
    assert [(read.entry, read.path) for read in output5.inputs] == [
        ("subanalysis.output1#u1", "results/u1/subanalysis.output1.json"),
        ("subanalysis.output1#subanalysis_u1", "subanalysis/results/u1/output1.json"),
        ("subanalysis.output1#v1", "subanalysis/results/v1/output1.json"),
        ("output1#subanalysis_v1", "subanalysis/results/v1/parent.output1.json"),
    ]
    owners = [read.result and str(read.result.owner) for read in output5.inputs]
    assert owners == [".", "subanalysis", "subanalysis", "subanalysis"]
    records = [read.result and read.result.places[0].record for read in output5.inputs]
    assert records == [
        ".astra/records/u1/subanalysis.output1.json",
        "subanalysis/.astra/records/u1/output1.json",
        "subanalysis/.astra/records/v1/output1.json",
        "subanalysis/.astra/records/v1/parent.output1.json",
    ]
    parent = output5.inputs[3].result
    assert parent is not None
    assert (parent.workdir, dict(parent.decisions)) == ("", {"decision1": "a"})
    assert render_command(parent, pinning) == (
        "python src/output1.py 'data/input1.csv' 'subanalysis/results/v1/output1.json' 'a' "
        "'subanalysis/results/v1/parent.output1.json'"
    )


def test_each_placeholder_renders_as_section_11s_table_says(pinning: Path) -> None:
    """§11 *The command as a template*: `{{` and `}}` are literal braces; `{inputs.<entry>}`,
    for entries with dots and `#`, the path of what the entry reads; `{decisions.<entry>}` the
    option selected; `{inputs}` every entry's path in order; `{output}` where the result is
    written; each verbatim, relative to the folder the recipe runs in or absolute."""
    plan = api.plan(pinning)
    (one, two) = [result for result in plan.results if result.output.id == "output3"]
    template = (
        "python make.py {x} '%(input1)s' '%(sub)s' '%(pinned)s' '%(option)s' "
        "%(input1)s %(sub)s %(pinned)s '%(output)s' }"
    )
    relative = {"input1": "data/input1.csv", "pinned": "results/u1/output1.json"}
    assert render_command(one, pinning) == template % {
        **relative,
        "sub": "results/u1/subanalysis.output1.json",
        "option": "a",
        "output": "results/u1/output3.csv",
    }
    assert render_command(two, ".") == template % {
        **relative,
        "sub": "results/u2/subanalysis.output1.json",
        "option": "b",
        "output": "results/u2/output3.csv",
    }
    assert render_command(one, pinning, absolute=True) == template % {
        "input1": pinning / "data/input1.csv",
        "pinned": pinning / "results/u1/output1.json",
        "sub": pinning / "results/u1/subanalysis.output1.json",
        "option": "a",
        "output": pinning / "results/u1/output3.csv",
    }


def test_a_driven_analysiss_recipe_runs_in_its_own_folder(pinning: Path) -> None:
    """§11 and §18: `subanalysis`'s recipe, built in the root's `u1`, runs in `subanalysis`'s
    folder and reads its own input there, and writes into the root's results."""
    plan = api.plan(pinning)
    (built,) = [r for r in plan.results if r.places[0].address == "subanalysis.output1#u1"]
    assert built.workdir == "subanalysis"
    folder = pinning / "subanalysis"
    assert render_command(built, folder) == (
        "python src/output1.py 'data/input1.csv' 'a' '../results/u1/subanalysis.output1.json'"
    )
    assert render_command(built, folder, absolute=True) == (
        f"python src/output1.py '{folder / 'data/input1.csv'}' 'a' "
        f"'{pinning / 'results/u1/subanalysis.output1.json'}'"
    )


CONDITIONAL = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
  decision3:
    when: [decision1.b]
    options: {a: {}, b: {}}
outputs:
  output1:
    type: metric
    format: json
    decisions: [decision1, decision3]
    recipe:
      command: python make.py '{decisions.decision1}' '{decisions.decision3}' '{output}'
universes:
  u1: {decisions: {decision1: a}}
  u2: {decisions: {decision1: b, decision3: a}}
"""
"""§9's `decision3`, active only where `decision1.b` is selected, in an output's `decisions`."""


def test_a_decision_inactive_where_a_result_is_built_selects_no_option(tmp_path: Path) -> None:
    """O30: in `u1`, `decision3` is inactive (§9) and no option is selected for it: the
    result's `decisions` holds None for the entry, `{decisions.decision3}` becomes the empty
    string, and the shape gives `null`."""
    plan = api.plan(repository(tmp_path, {"astra.yaml": CONDITIONAL}))
    one, two = plan.results
    assert (dict(one.decisions), dict(two.decisions)) == (
        {"decision1": "a", "decision3": None},
        {"decision1": "b", "decision3": "a"},
    )
    assert render_command(one, tmp_path) == "python make.py 'a' '' 'results/u1/output1.json'"
    assert render_command(two, tmp_path) == "python make.py 'b' 'a' 'results/u2/output1.json'"
    assert plan.to_json()["results"][0]["decisions"] == {"decision1": "a", "decision3": None}


# --- universes= and outputs= ---


def test_universes_narrow_the_plan_to_what_is_built_there_and_what_it_reads(
    worked: Path,
) -> None:
    assert results(api.plan(worked, universes=["u1"])) == [(".", "output1#u1")]
    assert results(api.plan(worked, outputs=["output2"], universes=["u2"])) == [
        (".", "output1#u1"),
        (".", "output1#u2"),
        (".", "output2"),
    ]
    assert results(api.plan(worked, outputs=["output1"], universes=["u2"])) == [(".", "output1#u2")]


def test_an_output_nothing_reads_is_built_on_request(pinning: Path) -> None:
    """An output of a declared analysis that no planned result reads isn't planned (§18), but
    can be asked for: it is planned as the root's own outputs are, in each of the root's
    universes where it is active (§9) and its analysis is built, and named from the root."""
    assert results(api.plan(pinning, outputs=["subanalysis.unread"])) == [
        (".", "subanalysis.unread#u1"),
        (".", "subanalysis.unread#u2"),
    ]
    assert results(api.plan(pinning, outputs=["subanalysis.cond"])) == [
        (".", "subanalysis.cond#u2")
    ]


@pytest.mark.parametrize(
    "universes, outputs, message",
    [
        (["u9"], None, "no universe `u9`: its universes are u1, u2"),
        (["subanalysis_u1"], None, "^`subanalysis_u1` is an import, which selects nothing: its"),
        (None, ["output9"], "`output9` names no output"),
        (["u1"], ["subanalysis.cond"], "`subanalysis.cond` has no result in the universes"),
        (None, ["subanalysis.reader"], "`reader` can't be built on request: `cond` reads"),
    ],
)
def test_what_isnt_there_is_a_request_error(
    pinning: Path, universes: list[str] | None, outputs: list[str] | None, message: str
) -> None:
    """A universe the root doesn't have, or an import; an address that names no output; an
    output with no result where it is asked for; and one that reads, in `u1`, an output
    inactive there (§13)."""
    with pytest.raises(api.RequestError, match=message.replace("(", r"\(")):
        api.plan(pinning, universes=universes, outputs=outputs)


# --- §18: a result with two names ---


INNER = """\
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

PAIR = """\
spec_version: "0.1.0"
analyses:
  stage: {path: stage}
  inner: {path: stage/inner}
outputs:
  through_inner:
    type: metric
    format: json
    inputs: [inner.output1]
    recipe:
      command: python make.py '{inputs.inner.output1}' '{output}'
  through_stage:
    type: metric
    format: json
    inputs: [stage.inner.output1]
    recipe:
      command: python make.py '{inputs.stage.inner.output1}' '{output}'
  through_staged:
    type: metric
    format: json
    inputs: [stage.staged]
    recipe:
      command: python make.py '{inputs.stage.staged}' '{output}'
universes:
  u1: {decisions: {inner.decision1: a}}
  u2: {decisions: {stage.inner.decision1: b}}
"""
"""§18: the root declares `inner` and `stage`, and `stage` declares the same folder as
`inner`; keys go through both. The root reads `inner`'s `output1` through each, and `stage`'s
`staged` reads it through `stage`'s `inner`."""

STAGE = """\
spec_version: "0.1.0"
analyses:
  inner: {path: inner}
outputs:
  staged:
    type: metric
    format: json
    inputs: [inner.output1]
    recipe:
      command: python make.py '{inputs.inner.output1}' '{output}'
"""


def test_a_result_reached_through_two_chains_has_a_place_for_each_name(tmp_path: Path) -> None:
    """§18 *Whose a result is, and its name*: `inner`'s `output1` is made once in each
    universe, and placed and recorded under `stage.inner.output1` and `inner.output1`. A
    recipe writes it at the first name's place, and reads it at the place of the name along
    the entry's declarations from the analysis the result belongs to, the root (O32): for
    `staged`'s `inner.output1`, along the root's `stage`, then `stage`'s `inner`."""
    files = {"astra.yaml": PAIR, "stage/astra.yaml": STAGE, "stage/inner/astra.yaml": INNER}
    top = repository(tmp_path, files)
    plan = api.plan(top)
    by_address = {result.places[0].address: result for result in plan.results}
    inner = by_address["inner.output1#u1"]
    assert inner.names == ("inner.output1", "stage.inner.output1")
    assert [(place.record, place.bytes) for place in inner.places] == [
        (".astra/records/u1/inner.output1.json", "results/u1/inner.output1.json"),
        (".astra/records/u1/stage.inner.output1.json", "results/u1/stage.inner.output1.json"),
    ]
    assert render_command(inner, top / "stage" / "inner") == (
        "python make.py 'a' '../../results/u1/inner.output1.json'"
    )
    assert render_command(by_address["through_inner#u1"], top) == (
        "python make.py 'results/u1/inner.output1.json' 'results/u1/through_inner.json'"
    )
    assert render_command(by_address["through_stage#u1"], top) == (
        "python make.py 'results/u1/stage.inner.output1.json' 'results/u1/through_stage.json'"
    )
    assert render_command(by_address["stage.staged#u1"], top / "stage") == (
        "python make.py '../results/u1/stage.inner.output1.json' '../results/u1/stage.staged.json'"
    )


# --- §17: an analysis from a commit ---


LIB = """\
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
  once:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
universes:
  v1:
    decisions: {d: b}
"""

FROM_COMMIT = """\
spec_version: "0.1.0"
analyses:
  lib: {path: lib, commit: "%s"}
outputs:
  result:
    type: table
    format: csv
    inputs: [lib.out, lib.out#v1, lib.once]
    recipe:
      command: python make.py {inputs} '{output}'
universes:
  u1:
    decisions: {lib.d: a}
"""
"""A root whose universes drive `lib` at a commit, and which reads `lib`'s `out` as it builds
it, pinned to `lib`'s own `v1`, and `lib`'s `once`, built once."""


def test_an_analysis_from_a_commit_is_read_through_its_records_unless_driven(
    tmp_path: Path,
) -> None:
    """§17 *Using one* and *Driving one*: what the root's universes build of `lib` is the
    root's, run on `lib`'s files at its commit (`run_at`); `lib`'s results in its own `v1`, and
    its output built once, though driven, are `lib`'s at that commit, read through their
    records (`read_only`), and no recipe of theirs runs (§21)."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL, "lib/astra.yaml": LIB})
    commit = git(top, "rev-parse", "HEAD").strip()
    repository(top, {"astra.yaml": FROM_COMMIT % commit})
    plan = api.plan(top)
    lib = Identity("lib", commit)
    assert {
        (str(r.owner), r.places[0].address): (r.read_only, r.run_at, r.workdir)
        for r in plan.results
    } == {
        (".", "lib.out#u1"): (False, commit, "lib"),
        (str(lib), "out#v1"): (True, None, "lib"),
        (str(lib), "once"): (True, None, "lib"),
        (".", "result#u1"): (False, None, ""),
    }
    (result,) = [r for r in plan.results if r.names == ("result",)]
    assert [(read.entry, read.path, read.commit) for read in result.inputs] == [
        ("lib.out", "results/u1/lib.out.json", None),
        ("lib.out#v1", "lib/results/v1/out.json", commit),
        ("lib.once", "lib/results/once.json", commit),
    ]


# --- the shape, and astra plan ---


def test_the_plan_as_astra_plan_1(worked: Path) -> None:
    """O28: the results in the plan's order, each read of a planned result by its index."""
    shape = api.plan(worked).to_json()
    assert (shape["shape"], shape["root"], len(shape["results"])) == (
        "astra-plan/1",
        "astra.yaml",
        3,
    )
    assert shape["results"][2] == {
        "names": ["output2"],
        "owner": {"folder": "", "commit": None},
        "output": {"analysis": {"folder": "", "commit": None}, "kind": "output", "id": "output2"},
        "universe": None,
        "places": [
            {
                "name": "output2",
                "address": "output2",
                "record": ".astra/records/output2.json",
                "bytes": "results/output2.csv",
            }
        ],
        "inputs": [
            {"entry": "output1#u1", "path": "results/u1/output1.json", "commit": None, "result": 0},
            {"entry": "output1#u2", "path": "results/u2/output1.json", "commit": None, "result": 1},
        ],
        "decisions": {},
        "command": (
            "python src/output2.py '{inputs.output1#u1}' '{inputs.output1#u2}' '{output}'"
        ),
        "workdir": "",
        "read_only": False,
        "run_at": None,
    }  # fmt: skip
    assert shape["results"][0]["universe"] == "u1"
    assert shape["results"][0]["decisions"] == {"decision1": "a"}


def test_astra_plan_shows_each_result_with_its_places_and_command(worked: Path) -> None:
    result = astra("plan", str(worked))
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "output1#u1",
        "  record   .astra/records/u1/output1.json",
        "  bytes    results/u1/output1.json",
        "  run in   .",
        "  command  python src/output1.py 'data/input1.csv' 'a' 'results/u1/output1.json'",
        "output1#u2",
        "  record   .astra/records/u2/output1.json",
        "  bytes    results/u2/output1.json",
        "  run in   .",
        "  command  python src/output1.py 'data/input1.csv' 'b' 'results/u2/output1.json'",
        "output2",
        "  record   .astra/records/output2.json",
        "  bytes    results/output2.csv",
        "  run in   .",
        "  command  python src/output2.py 'results/u1/output1.json' 'results/u2/output1.json' "
        "'results/output2.csv'",
        "3 planned result(s)",
    ]
    shape = json.loads(astra("plan", str(worked), "--json").stdout)
    assert shape == api.plan(worked).to_json()


def test_an_invalid_analysis_has_no_plan(tmp_path: Path) -> None:
    """O27: `astra plan` prints the validation report, as `astra validate` does, and exits 1;
    `api.plan` raises InvalidAnalysisError with the report."""
    broken = WORKED_EXAMPLE.replace("{decision1: b}", "{decision1: c}")
    top = repository(tmp_path, {"astra.yaml": broken, "data/input1.csv": "1\n"})
    with pytest.raises(api.InvalidAnalysisError) as raised:
        api.plan(top)
    assert [d.code for d in raised.value.report.diagnostics] == ["UNKNOWN_OPTION"]
    result = astra("plan", str(top))
    assert result.exit_code == 1
    assert "UNKNOWN_OPTION" in result.stdout
    result = astra("plan", str(top), "--json")
    assert result.exit_code == 1
    assert json.loads(result.stdout)["shape"] == "astra-validation-report/1"


def test_astra_plan_exits_2_where_there_is_no_analysis(tmp_path: Path) -> None:
    result = astra("plan", str(git_init(tmp_path)))
    assert result.exit_code == 2
    assert "has no astra.yaml" in result.stderr
