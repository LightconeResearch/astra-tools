"""The plan (design §4.6): §18's planned results, each after what it reads, with their names,
owners, places, inputs, decisions and commands; `render_command` (§11 *The command as a
template*); §17's results read through their records or run at a commit; `api.plan`, its
shape `astra-plan/1`, and `astra plan`.

The stacks are §2's worked example; astra-spec's `examples/iris_pipeline`; §16's `output5`
reading §15's `subanalysis` in three universes, where `subanalysis`'s own `v1` drives its
parent (§18), with an output of every placeholder; an analysis with a declaration no key
drives, for outputs asked for that aren't built; §18's `inner` reached through `inner` and
`stage.inner`; §17's analysis from a commit, driven and pinned; an analysis whose recipes ask for
resources; and one with each note a stack read where the root is can have (design §4.6).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.cli import main
from astra.model import Resources
from astra.plan import Plan, outside, render_command
from astra.records import new_record
from astra.stack import Identity
from tests.conftest import ENVIRONMENT, MINIMAL, RUNNER, SPEC, git, git_init, repository
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


@pytest.fixture(scope="module")
def pinning(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {
        "astra.yaml": ROOT.replace("universes:\n", PLACEHOLDERS + "universes:\n", 1),
        "data/input1.csv": "1\n",
        "subanalysis/astra.yaml": SUBANALYSIS,
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
    universes where its analysis is built, and named from the root."""
    assert results(api.plan(pinning, outputs=["subanalysis.unread"])) == [
        (".", "subanalysis.unread#u1"),
        (".", "subanalysis.unread#u2"),
    ]


@pytest.mark.parametrize(
    "universes, outputs, message",
    [
        (["u9"], None, "no universe `u9`: its universes are u1, u2"),
        (["subanalysis_u1"], None, "^`subanalysis_u1` is an import, which selects nothing: its"),
        (None, ["output9"], "`output9` names no output"),
    ],
)
def test_what_isnt_there_is_a_request_error(
    pinning: Path, universes: list[str] | None, outputs: list[str] | None, message: str
) -> None:
    """A universe the root doesn't have, or an import; an address that names no output."""
    with pytest.raises(api.RequestError, match=message.replace("(", r"\(")):
        api.plan(pinning, universes=universes, outputs=outputs)


UNDRIVEN = """\
spec_version: "0.1.0"
analyses:
  stage: {path: stage}
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
universes:
  u1: {decisions: {decision1: a}}
  u2: {decisions: {decision1: b}}
"""
"""A root whose universes drive `stage`, which has no decisions to set, and set no key
through `stage.lone`; nothing they plan uses `lone`'s decision, so they drive `lone` too, with
nothing to set (§16; Elements)."""

READS_LONE = """\
spec_version: "0.1.0"
analyses:
  lone: {path: ../lone}
outputs:
  reader:
    type: metric
    format: json
    inputs: [lone.out]
    recipe:
      command: python make.py '{inputs.lone.out}' '{output}'
"""
"""`stage`, with no decisions, whose `reader` reads `lone`'s `out` without a pin."""

LONE = """\
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
"""
"""An analysis whose `out`, listing its decision `d`, is built per universe."""


def test_an_output_asked_for_with_no_result_to_give_is_a_request_error(tmp_path: Path) -> None:
    """design §4.6, §16 *The universe being built*: the root's universes drive `stage` and,
    through it, `lone`, as nothing they plan uses `lone`'s `d` (Elements), so they set it
    nowhere. `stage.lone.out` lists `d`, and `stage.reader`, built in each, reads `lone.out`:
    asked for, either would use `d` where it isn't set (Results *uses*). Nothing planned reads
    either, so the stack breaks no rule."""
    files = {"astra.yaml": UNDRIVEN, "stage/astra.yaml": READS_LONE, "lone/astra.yaml": LONE}
    top = repository(tmp_path, files)
    assert api.validate(top).diagnostics == ()
    with pytest.raises(
        api.RequestError,
        match="^`stage.lone.out` can't be built on request in `u1`: it, or what it reads, uses "
        "`stage.lone.d`, which",
    ):
        api.plan(top, outputs=["stage.lone.out"])
    with pytest.raises(
        api.RequestError,
        match="^`stage.reader` can't be built on request in `u1`: it, or what it reads, uses "
        "`stage.lone.d`, which",
    ):
        api.plan(top, outputs=["stage.reader"])


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
    """§18 *Which analysis a result belongs to, and its name* and *Where records and bytes go*:
    `inner`'s `output1` is made once in each universe, and placed and recorded under
    `stage.inner.output1` and `inner.output1`. A recipe writes it at the first name's place, and
    reads it at the place of the name along the entry's declarations from the analysis the result
    belongs to, the root: for `staged`'s `inner.output1`, along the root's `stage`, then `stage`'s
    `inner`."""
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
    """§17 *Using one*: what the root's universes build of `lib` is the
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


def test_an_entry_read_at_a_commit_is_where_the_runner_put_its_bytes(tmp_path: Path) -> None:
    """§17, §21: what `result` reads of `lib` at its commit is in that commit's tree, not the
    checkout's, so its path is git's `<commit>:<path>` until the runner says where it put the
    bytes it got (`got`), from the checkout's top or absolute; and `new_record` hashes them
    there, refusing an entry `got` doesn't give."""
    top = repository(tmp_path / "repo", {"astra.yaml": MINIMAL, "lib/astra.yaml": LIB})
    commit = git(top, "rev-parse", "HEAD").strip()
    repository(top, {"astra.yaml": FROM_COMMIT % commit})
    (result,) = [r for r in api.plan(top).results if r.names == ("result",)]
    assert render_command(result, top) == (
        f"python make.py results/u1/lib.out.json {commit}:lib/results/v1/out.json "
        f"{commit}:lib/results/once.json 'results/u1/result.csv'"
    )
    got = {"lib.out#v1": "../got/out.json", "lib.once": str(tmp_path / "got" / "once.json")}
    assert render_command(result, top, got=got) == (
        "python make.py results/u1/lib.out.json ../got/out.json ../got/once.json "
        "'results/u1/result.csv'"
    )
    (tmp_path / "got").mkdir()
    for name, data in (("out.json", b"1\n"), ("once.json", b"22\n")):
        (tmp_path / "got" / name).write_bytes(data)
    for path in ("results/u1/lib.out.json", "results/u1/result.csv"):
        (top / path).parent.mkdir(parents=True, exist_ok=True)
        (top / path).write_bytes(b"0\n")
    made = {"checkout": top, "commit": commit, "environment": ENVIRONMENT, "runner": RUNNER}
    with pytest.raises(ValueError, match="lib.out#v1"):
        new_record(result, **made)
    (record,) = new_record(result, **made, got=got)
    assert [(item.entry, item.size) for item in record.inputs] == [
        ("lib.out", 2),
        ("lib.out#v1", 2),
        ("lib.once", 3),
    ]


# --- the shape, and astra plan ---


def test_the_plan_as_astra_plan_1(worked: Path) -> None:
    """The results in the plan's order, each read of a planned result by its index."""
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
            {"entry": "output1#u1", "path": "results/u1/output1.json", "commit": None, "result": 0,
             "via": []},
            {"entry": "output1#u2", "path": "results/u2/output1.json", "commit": None, "result": 1,
             "via": []},
        ],
        "decisions": {},
        "command": (
            "python src/output2.py '{inputs.output1#u1}' '{inputs.output1#u2}' '{output}'"
        ),
        "workdir": "",
        "read_only": False,
        "run_at": None,
        "resources": None,
    }  # fmt: skip
    assert shape["results"][0]["universe"] == "u1"
    assert shape["results"][0]["decisions"] == {"decision1": "a"}
    assert shape["notes"] == []


def test_astra_plan_shows_each_result_with_its_places_and_command(worked: Path) -> None:
    result = astra("plan", str(worked))
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "output1#u1",
        "  record    .astra/records/u1/output1.json",
        "  bytes     results/u1/output1.json",
        "  run in    .",
        "  command   python src/output1.py 'data/input1.csv' 'a' 'results/u1/output1.json'",
        "output1#u2",
        "  record    .astra/records/u2/output1.json",
        "  bytes     results/u2/output1.json",
        "  run in    .",
        "  command   python src/output1.py 'data/input1.csv' 'b' 'results/u2/output1.json'",
        "output2",
        "  record    .astra/records/output2.json",
        "  bytes     results/output2.csv",
        "  run in    .",
        "  command   python src/output2.py 'results/u1/output1.json' 'results/u2/output1.json' "
        "'results/output2.csv'",
        "3 planned result(s)",
    ]
    shape = json.loads(astra("plan", str(worked), "--json").stdout)
    assert shape == api.plan(worked).to_json()


# --- what a recipe asks for, and the plan's notes (design §4.6) ---


ASKING = """\
spec_version: "0.1.0"
outputs:
  default:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
  own:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
      resources: {cpus: 0.5, memory: 4GB, gpus: 1}
"""
"""An analysis with a recipe that asks for resources, and one that asks for none."""


def test_each_result_carries_what_its_recipe_asks_for(tmp_path: Path) -> None:
    """§11, design §4.6: a result carries its recipe's `resources`, as written, which a runner
    schedules with. `astra-plan/1` gives them, and `astra plan` shows them."""
    top = repository(tmp_path, {"astra.yaml": ASKING})
    plan = api.plan(top)
    default, own = plan.results
    assert default.resources is None
    assert own.resources == Resources(cpus=0.5, memory="4GB", gpus=1)
    assert [r["resources"] for r in plan.to_json()["results"]] == [
        None,
        {"cpus": 0.5, "memory": "4GB", "gpus": 1},
    ]
    assert astra("plan", str(top)).stdout.splitlines() == [
        "default",
        "  record    .astra/records/default.json",
        "  bytes     results/default.json",
        "  run in    .",
        "  command   python make.py 'results/default.json'",
        "own",
        "  record    .astra/records/own.json",
        "  bytes     results/own.json",
        "  run in    .",
        "  resources cpus 0.5, memory 4GB, gpus 1",
        "  command   python make.py 'results/own.json'",
        "2 planned result(s)",
    ]


def test_the_plan_notes_a_pin_that_names_another_analysiss_universe_by_the_fallback(
    pinning: Path,
) -> None:
    """design §4.6, §16 *Pins and imported universes*: the root's `subanalysis.output1#v1`
    names `subanalysis`'s `v1` only because the root's file has no universe `v1`, so adding one
    would change what it names. That is noted, though it breaks no rule; the pins naming the
    root's own `u1` and its imports aren't."""
    plan = api.plan(pinning)
    (note,) = [note for note in plan.notes if note.kind == "fallback_pin"]
    assert note.results == ()
    assert note.location is not None
    assert (note.location.file, note.location.pointer) == (
        "astra.yaml",
        "/outputs/output5/inputs/2",
    )
    assert note.message == (
        "`subanalysis.output1#v1` names `v1` of `subanalysis` only because this file has no "
        "universe `v1`: adding one, or an import of that id, would change what it names"
    )
    (shaped,) = [note for note in plan.to_json()["notes"] if note["kind"] == "fallback_pin"]
    assert shaped == {
        "kind": "fallback_pin",
        "message": note.message,
        "location": {
            "file": "astra.yaml",
            "pointer": "/outputs/output5/inputs/2",
            "line": note.location.line,
            "column": note.location.column,
            "key": None,
            "commit": None,
            "url": None,
        },
        "results": [],
        "built": True,
        "universes": [],
        "switch": None,
        "option": None,
    }
    where = f"astra.yaml:{note.location.line}:{note.location.column}"
    assert f"note {where} {note.message}" in astra("plan", str(pinning), "--notes").stdout
    assert (
        "  1 pin(s) name another analysis's universe only because their file has none of that id"
        in astra("plan", str(pinning)).stdout
    )


def test_the_plan_notes_each_result_with_two_names(tmp_path: Path) -> None:
    """design §4.6, §18: `inner`'s `output1`, reached through `inner` and `stage.inner`, has two
    names in each universe. Each is noted, though `RESULT_IN_TWO_PLACES` is only a SHOULD, and
    `astra-plan/1` gives the result by its index."""
    files = {"astra.yaml": PAIR, "stage/astra.yaml": STAGE, "stage/inner/astra.yaml": INNER}
    top = repository(tmp_path, files)
    plan = api.plan(top)
    assert [(note.kind, note.location) for note in plan.notes] == [("two_names", None)] * 2
    assert [[r.places[0].address for r in note.results] for note in plan.notes] == [
        ["inner.output1#u1"],
        ["inner.output1#u2"],
    ]
    assert plan.notes[0].message == (
        "one result has the names `inner.output1#u1`, `stage.inner.output1#u1`: it is made "
        "once and placed under each, as its analysis is driven through two chains of "
        "declarations"
    )
    shaped = plan.to_json()
    for note in shaped["notes"]:
        (index,) = note["results"]
        assert shaped["results"][index]["names"] == ["inner.output1", "stage.inner.output1"]
    lines = astra("plan", str(top), "--notes").stdout.splitlines()
    assert lines[-4:] == [
        f"note {plan.notes[0].message}",
        f"note {plan.notes[1].message}",
        f"{len(plan.results)} planned result(s), and notes, none of them a breach:",
        "  2 result(s) have two names",
    ]


NOTED = """\
spec_version: "0.1.0"
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options: {a: {}, b: {}, c: {}}
  decision2:
    options: {x: {}, y: {}}
outputs:
  first:
    type: metric
    format: json
    inputs: [input1]
    decisions: [decision1]
    recipe:
      command: PYTHONPATH=../lib python -m first '{inputs.input1}' '{decisions.decision1}' {output}
  second:
    type: metric
    format: json
    inputs: [first]
    recipe:
      command: python src/second.py '{inputs.first}' '{output}'
  third:
    type: metric
    format: json
    inputs: [first]
    decisions: [decision2]
    recipe:
      command: python src/third.py '{inputs.first}' '{decisions.decision2}' '{output}'
universes:
  u1: {decisions: {decision1: a, decision2: x}}
  u2: {decisions: {decision1: a, decision2: y}}
  u3: {decisions: {decision1: b, decision2: x}}
"""
"""`first` selects the same option of `decision1` in `u1` and `u2`, so it is one computation
there, and so is `second`, which reads it; `third` selects `decision2` too, which differs.
`first`'s command names `../lib`."""

NO_UNIVERSES = """\
spec_version: "0.1.0"
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  never:
    type: figure
    format: png
    decisions: [decision1]
    recipe:
      command: python src/never.py '{decisions.decision1}' '{output}'
"""
"""A root with no universes, whose `never` is built per universe."""


def test_the_plan_notes_each_output_with_no_planned_result(pinning: Path, tmp_path: Path) -> None:
    """design §4.6, §18: an output of a declared analysis that no planned result reads and the
    root's evidence doesn't cite, and an output of the root built per universe where the root
    has no universes, have no planned result, so a check of the root never covers them. Each is
    noted at the output, in the files read where the root is."""
    found = [note for note in api.plan(pinning).notes if note.kind == "unplanned"]
    assert [(n.location and n.location.file, n.location and n.location.pointer) for n in found] == [
        ("subanalysis/astra.yaml", "/outputs/unread")
    ]
    assert found[0].message == (
        "`unread` has no planned result: no planned result reads it and the root's evidence "
        "doesn't cite it, so a check of the root never covers it"
    )
    top = repository(tmp_path, {"astra.yaml": NO_UNIVERSES})
    (never,) = [note for note in api.plan(top).notes if note.kind == "unplanned"]
    assert never.location is not None
    assert (never.location.pointer, never.results) == ("/outputs/never", ())
    assert never.message == (
        "`never` has no planned result: it is built per universe and the root has no universes, "
        "so a check of the root never covers it"
    )


def test_the_plan_notes_results_that_are_one_computation_in_several_universes(
    pinning: Path, tmp_path: Path
) -> None:
    """design §4.6: results of one output that read the same files and the same computations,
    with the same options selected, are one computation, which a runner can build once and
    place at each. The root's `u1` and `subanalysis`'s own `u1` both select `a` for
    `subanalysis`'s `decision1`, so its `output1` is one computation in both; each result is
    named in its owner's terms."""
    top = repository(tmp_path, {"astra.yaml": NOTED, "data/input1.csv": "1\n"})
    plan = api.plan(top)
    found = [note for note in plan.notes if note.kind == "same_computation"]
    assert [[r.places[0].address for r in note.results] for note in found] == [
        ["first#u1", "first#u2"],
        ["second#u1", "second#u2"],
    ]
    assert found[0].location is None
    assert found[0].message == (
        "`first#u1`, `first#u2` are one computation, with the same command, inputs and selected "
        "options: a runner can build one and place its bytes at each"
    )
    index = {r.places[0].address: at for at, r in enumerate(plan.results)}
    shaped = [note for note in plan.to_json()["notes"] if note["kind"] == "same_computation"]
    assert [note["results"] for note in shaped] == [
        [index["first#u1"], index["first#u2"]],
        [index["second#u1"], index["second#u2"]],
    ]
    found = [note for note in api.plan(pinning).notes if note.kind == "same_computation"]
    assert [[r.places[0].address for r in note.results] for note in found] == [
        ["subanalysis.output1#u1", "output1#u1"],
        ["subanalysis.output1#u2", "output1#v1"],
    ]
    assert found[0].message.startswith(
        "`subanalysis.output1#u1`, `output1#u1` of `subanalysis` are one computation"
    )


@pytest.mark.parametrize(
    ("command", "climbing"),
    [
        ("python ../../src/x.py '{output}'", ("../../src/x.py",)),
        ("PYTHONPATH=../lib:{inputs.code}/src python -m x", ("../lib",)),
        ("python x.py --config=../c.yaml 2>../log", ("../c.yaml", "../log")),
        ("cd .. && make", ("..",)),
        ('bash -c "python ../x.py" && cat ../x.py', ("../x.py",)),
        ("python src/../x.py a/b/../../c", ()),
        ("python src/../../x.py", ("src/../../x.py",)),
        ("python {inputs.data}/../x.py {output}", ()),
        ("/usr/bin/env python /opt/../x.py", ()),
        ("awk '{{print $1}}' x | seq 1..3 > ...", ()),
    ],
)
def test_a_command_names_a_path_outside_its_folder_where_it_climbs_out(
    command: str, climbing: tuple[str, ...]
) -> None:
    """design §4.6, §11: a path climbs out of the folder the recipe runs in where its `..`
    outnumber the folders before them. A path from a placeholder starts elsewhere, and an
    absolute path names no folder of the analysis."""
    assert outside(command) == climbing


def test_the_plan_notes_each_command_that_names_a_path_outside_its_folder(tmp_path: Path) -> None:
    """design §4.6, §21 `CODE_OUTSIDE_ANALYSIS`: `first`'s command names `../lib`, outside the
    root's folder, and `second`'s names `sub/second.py`, inside `sub`, which holds an
    `astra.yaml` of its own, declared or not. Each is noted at the command, citing the rule,
    which a runner holds a recipe to; `third`'s `src/third.py` is the root's own."""
    files = {
        "astra.yaml": NOTED.replace("python src/second.py", "python ./sub/second.py"),
        "data/input1.csv": "1\n",
        "sub/astra.yaml": MINIMAL,
    }
    top = repository(tmp_path, files)
    found = [note for note in api.plan(top).notes if note.kind == "outside_folder"]
    assert [note.location and note.location.pointer for note in found] == [
        "/outputs/first/recipe/command",
        "/outputs/second/recipe/command",
    ]
    rule = (
        "a recipe should run only code tracked in its analysis's folder, outside every folder "
        "below it that holds an analysis of its own, or that its output's inputs give it "
        "(`CODE_OUTSIDE_ANALYSIS`)"
    )
    assert [note.message for note in found] == [
        f"the command names `../lib`, outside its analysis's folder: {rule}",
        f"the command names `./sub/second.py`, inside `sub`, which holds an analysis of its own: "
        f"{rule}",
    ]
    assert all(note.results == () for note in found)


BUILDS = {
    "astra.yaml": """\
spec_version: "0.1.0"
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options: {a: {}, b: {}}
outputs:
  result:
    type: metric
    format: json
    decisions: [decision1]
    recipe:
      command: python make.py '{decisions.decision1}' '{output}'
  other:
    type: metric
    format: json
    recipe:
      command: python ../tools/other.py '{output}'
universes:
  u1: {decisions: {decision1: a}}
""",
    "data/input1.csv": "1\n",
    "sub/astra.yaml": """\
spec_version: "0.1.0"
analyses:
  paper: {path: ..}
  inner: {path: inner}
outputs:
  read:
    type: metric
    format: json
    inputs: [paper.input1, paper.result#u1]
    recipe:
      command: python read.py '{inputs.paper.input1}' '{inputs.paper.result#u1}' '{output}'
""",
    "sub/inner/astra.yaml": """\
spec_version: "0.1.0"
analyses:
  paper: {path: ../..}
outputs:
  pinned:
    type: metric
    format: json
    inputs: [paper.result#u1]
    recipe:
      command: python ../pinned.py '{inputs.paper.result#u1}' '{output}'
""",
}
"""`sub` reads from the analysis above it, none of whose decisions a universe of `sub` uses (it
has none), so it has nothing to set and `sub` builds it without a key (Elements). It also builds
`inner`, which has no decisions, and plans none of `inner`'s outputs. Both pin `paper.result#u1`
by the fallback, and only `sub`'s pin is read through. A command of each climbs out of its
folder."""


def test_the_plan_notes_say_whether_they_concern_what_the_root_builds(tmp_path: Path) -> None:
    """design §4.6: a fallback pin concerns what the root builds where a planned result reads
    through it, and an output with no planned result, or a command naming a path outside its
    analysis, where its analysis is the root or one the root drives. `astra plan` counts and
    lists those, and gives the whole stack's count of a kind on a line of its own where it is
    more (here, the fallback pins); the JSON lists every note, with `built`."""
    sub = repository(tmp_path, BUILDS) / "sub"
    plan = api.plan(sub)
    found = [(note.kind, note.location and note.location.file, note.built) for note in plan.notes]
    assert found == [
        ("fallback_pin", "sub/astra.yaml", True),
        ("fallback_pin", "sub/inner/astra.yaml", False),
        ("unplanned", "astra.yaml", True),
        ("unplanned", "sub/inner/astra.yaml", True),
        ("outside_folder", "astra.yaml", True),
        ("outside_folder", "sub/inner/astra.yaml", True),
    ]
    lines = astra("plan", str(sub), "--notes").stdout.splitlines()
    listed = [line for line in lines if line.startswith("note ")]
    assert [line.split(" ", 2)[1].split(":")[0] for line in listed] == [
        "sub/astra.yaml",
        "astra.yaml",
        "sub/inner/astra.yaml",
        "astra.yaml",
        "sub/inner/astra.yaml",
    ]
    assert lines[-5:] == [
        f"{len(plan.results)} planned result(s), and notes, none of them a breach:",
        "  1 pin(s) name another analysis's universe only because their file has none of that id",
        "  2 pin(s) in the whole stack name another analysis's universe only because their file "
        "has none of that id",
        "  2 output(s) have no planned result",
        "  2 command(s) name a path outside their analysis (CODE_OUTSIDE_ANALYSIS)",
    ]
    shaped = json.loads(astra("plan", str(sub), "--json").stdout)["notes"]
    assert [note["built"] for note in shaped] == [True, False, True, True, True, True]


def test_astra_plan_counts_the_notes_by_kind_and_lists_them_on_request(tmp_path: Path) -> None:
    """design §4.6: `astra plan` counts the notes by kind after the results, and `--notes`
    lists each one first. The JSON always lists them."""
    top = repository(tmp_path, {"astra.yaml": NOTED, "data/input1.csv": "1\n"})
    plan = api.plan(top)
    counts = [
        "  2 computation(s) repeated across universes, in 4 result(s)",
        "  1 command(s) name a path outside their analysis (CODE_OUTSIDE_ANALYSIS)",
    ]
    lines = astra("plan", str(top)).stdout.splitlines()
    assert not any(line.startswith("note ") for line in lines)
    assert lines[-3:] == [
        f"{len(plan.results)} planned result(s), and notes, none of them a breach "
        "(--notes lists them):",
        *counts,
    ]
    lines = astra("plan", str(top), "--notes").stdout.splitlines()
    listed = [line for line in lines if line.startswith("note ")]
    assert all(line.endswith(note.message) for line, note in zip(listed, plan.notes, strict=True))
    assert lines[-3:] == [
        f"{len(plan.results)} planned result(s), and notes, none of them a breach:",
        *counts,
    ]
    assert len(json.loads(astra("plan", str(top), "--json", "--notes").stdout)["notes"]) == 3


def test_an_invalid_analysis_has_no_plan(tmp_path: Path) -> None:
    """`astra plan` prints the validation report, as `astra validate` does, and exits 1;
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
