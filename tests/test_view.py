"""The universe view (design §4.6): the stack as it is in one of the root's universes, each
analysis built there or not (§16), each decision active or not and its option selected (§9,
§12), each output's planned result there and its places (§18); `api.view`, its shape
`astra-universe-view/1`, and `astra view`.

The stack is §2's worked example, with §9's `decision3` and `output4`, a `subanalysis` the
root's universes drive (§16), and an `other` they don't, read pinned to its own `v1`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.cli import main
from astra.stack import Identity
from astra.view import UniverseView
from tests.conftest import MINIMAL, git, git_init, repository
from tests.test_plan import FROM_COMMIT, LIB

ROOT = """\
spec_version: "0.1.0"
analyses:
  subanalysis: {path: subanalysis}
  other: {path: other}
inputs:
  input1: {path: data/input1.csv}
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
    inputs: [input1, subanalysis.output1]
    decisions: [decision1]
    recipe:
      command: >-
        python src/output1.py '{inputs.input1}' '{inputs.subanalysis.output1}'
        '{decisions.decision1}' '{output}'
  output2:
    type: table
    format: csv
    inputs: [output1#u1, output1#u2, other.out#v1]
    recipe:
      command: python src/output2.py {inputs} '{output}'
  output4:
    type: figure
    format: png
    when: [decision1.b]
    recipe:
      command: python src/output4.py '{output}'
universes:
  u1:
    decisions: {decision1: a, subanalysis.decision1: a}
  u2:
    decisions: {decision1: b, decision3: a, subanalysis.decision1: b}
"""

SUBANALYSIS = """\
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
  unread:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
"""

OTHER = """\
spec_version: "0.1.0"
decisions:
  d:
    options: {a: {}, b: {}}
  e:
    when: [d.b]
    options: {a: {}, b: {}}
outputs:
  out:
    type: metric
    format: json
    decisions: [d]
    recipe:
      command: python make.py '{decisions.d}' '{output}'
universes:
  v1:
    decisions: {d: b, e: a}
"""


def astra(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


@pytest.fixture(scope="module")
def top(tmp_path_factory: pytest.TempPathFactory) -> Path:
    files = {
        "astra.yaml": ROOT,
        "data/input1.csv": "1\n",
        "subanalysis/astra.yaml": SUBANALYSIS,
        "other/astra.yaml": OTHER,
    }
    return repository(tmp_path_factory.mktemp("view"), files)


def state(view: UniverseView) -> dict[str, object]:
    """Each analysis by folder: whether it is built, and each decision's activity and option,
    and each output's activity and the addresses of its result there."""
    return {
        analysis.member.identity.folder or ".": (
            analysis.built,
            {id_: (d.active, d.selected) for id_, d in analysis.decisions.items()},
            {id_: (o.active, [p.address for p in o.places]) for id_, o in analysis.outputs.items()},
        )
        for analysis in view.analyses
    }


def test_the_view_in_u1(top: Path) -> None:
    """§9: `decision3` and `output4` are inactive where `decision1.a` is selected. §16: the
    root's universes drive `subanalysis`, so it is built in `u1`, with its `decision1` set to
    `a`; its `output1` has the root's result there (§18), and `unread`, which nothing reads,
    none. `other` isn't built in `u1`: no option is selected for its decisions, `e`'s `when`
    tests a decision `u1` leaves unset (O16), and its `out` has no result in `u1`."""
    view = api.view("u1", top)
    assert (view.root, view.universe) == ("astra.yaml", "u1")
    assert state(view) == {
        ".": (
            True,
            {"decision1": (True, "a"), "decision3": (False, None)},
            {
                "output1": (True, ["output1#u1"]),
                "output2": (True, ["output2"]),
                "output4": (False, []),
            },
        ),
        "subanalysis": (
            True,
            {"decision1": (True, "a")},
            {"output1": (True, ["subanalysis.output1#u1"]), "unread": (True, [])},
        ),
        "other": (False, {"d": (True, None), "e": (None, None)}, {"out": (True, [])}),
    }
    sub = view.analyses[1].outputs["output1"]
    assert sub.result is not None and sub.result.owner == Identity("")
    assert [(place.record, place.bytes) for place in sub.places] == [
        (".astra/records/u1/subanalysis.output1.json", "results/u1/subanalysis.output1.json")
    ]


def test_the_view_in_u2(top: Path) -> None:
    """§9: `decision1.b` switches `decision3` and `output4` on."""
    root = state(api.view("u2", top))["."]
    assert root == (
        True,
        {"decision1": (True, "b"), "decision3": (True, "a")},
        {
            "output1": (True, ["output1#u2"]),
            "output2": (True, ["output2"]),
            "output4": (True, ["output4#u2"]),
        },
    )


def test_the_view_as_astra_universe_view_1(top: Path) -> None:
    """O29: each analysis with its fields as its file writes them."""
    shape = api.view("u1", top).to_json()
    assert [shape[key] for key in ("shape", "root", "universe")] == [
        "astra-universe-view/1",
        "astra.yaml",
        "u1",
    ]
    root, sub, other = shape["analyses"]
    assert [root[key] for key in ("folder", "commit", "file", "built")] == [
        "",
        None,
        "astra.yaml",
        True,
    ]
    assert root["fields"]["universes"]["u1"] == {
        "decisions": {"decision1": "a", "subanalysis.decision1": "a"}
    }
    assert root["decisions"]["decision3"] == {"active": False, "selected": None}
    assert root["outputs"]["output4"] == {"active": False, "result": None}
    assert sub["outputs"]["output1"] == {
        "active": True,
        "result": {
            "names": ["subanalysis.output1"],
            "owner": {"folder": "", "commit": None},
            "universe": "u1",
            "places": [
                {
                    "name": "subanalysis.output1",
                    "address": "subanalysis.output1#u1",
                    "record": ".astra/records/u1/subanalysis.output1.json",
                    "bytes": "results/u1/subanalysis.output1.json",
                }
            ],
        },
    }
    assert (other["built"], other["decisions"]["e"]) == (False, {"active": None, "selected": None})


def test_astra_view_shows_the_stack_in_one_universe(top: Path) -> None:
    result = astra("view", "u1", str(top))
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "universe u1",
        "astra.yaml  built",
        "  decision1    a",
        "  decision3    inactive",
        "  output1      output1#u1  results/u1/output1.json",
        "  output2      output2  results/output2.csv",
        "  output4      inactive",
        "subanalysis/astra.yaml  built",
        "  decision1    a",
        "  output1      subanalysis.output1#u1  results/u1/subanalysis.output1.json",
        "  unread       no planned result",
        "other/astra.yaml  not built in u1",
        "  d            no option selected",
        "  e            no option selected",
        "  out          no planned result",
    ]
    shape = json.loads(astra("view", "u1", str(top), "--json").stdout)
    assert shape == api.view("u1", top).to_json()


def test_astra_view_names_the_commit_of_an_analysis_from_a_commit(tmp_path: Path) -> None:
    """§17: the root's universes drive `lib`, read at a commit, so it is built in `u1`, where
    its `out` is the root's; its `once`, built once, is `lib`'s, at that commit (§18)."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL, "lib/astra.yaml": LIB})
    commit = git(top, "rev-parse", "HEAD").strip()
    repository(top, {"astra.yaml": FROM_COMMIT % commit})
    result = astra("view", "u1", str(top))
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "universe u1",
        "astra.yaml  built",
        "  result       result#u1  results/u1/result.csv",
        f"lib/astra.yaml at {commit}  built",
        "  d            a",
        "  out          lib.out#u1  results/u1/lib.out.json",
        f"  once         once  lib/results/once.json at {commit}",
    ]


@pytest.mark.parametrize("universe", ["u9", "v1"])
def test_astra_view_of_a_universe_the_root_hasnt_is_a_usage_error(top: Path, universe: str) -> None:
    """`v1` is `other`'s universe, not the root's."""
    result = astra("view", universe, str(top))
    assert result.exit_code == 2
    assert f"no universe `{universe}`: its universes are u1, u2" in result.stderr


def test_an_invalid_analysis_has_no_view(tmp_path: Path) -> None:
    """O27: `astra view` prints the validation report, as `astra validate` does, and exits 1."""
    files = {"astra.yaml": ROOT.replace("decision3: a, ", ""), "data/input1.csv": "1\n"}
    files |= {"subanalysis/astra.yaml": SUBANALYSIS, "other/astra.yaml": OTHER}
    folder = repository(tmp_path, files)
    with pytest.raises(api.InvalidAnalysisError):
        api.view("u1", folder)
    result = astra("view", "u1", str(folder))
    assert result.exit_code == 1
    assert "MISSING_DECISION" in result.stdout
    result = astra("view", "u1", str(folder), "--json")
    assert (result.exit_code, json.loads(result.stdout)["valid"]) == (1, False)


def test_astra_view_exits_2_where_there_is_no_analysis(tmp_path: Path) -> None:
    assert astra("view", "u1", str(git_init(tmp_path))).exit_code == 2
