"""The universe view: the stack as it is in one of the root's universes, each analysis built
there or not, each decision, whether the universe uses it (Results *uses*) and its option
selected, each output, whether it is built there (Results *built*), and its planned result
there and its places; `api.view`, its shape `astra-universe-view/1`, and `astra view`.

The stack is the worked example, with a `subanalysis` the root's universes drive, and an
`other` they drive with nothing to set, as no universe of the root uses its decisions (Elements),
read pinned to its own `v1`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.cli import main
from astra.stack import Identity
from astra.view import UniverseView
from tests.conftest import repository

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
universes:
  u1:
    decisions: {decision1: a, subanalysis.decision1: a}
  u2:
    decisions: {decision1: b, subanalysis.decision1: b}
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
    options: {a: {}, b: {}}
outputs:
  out:
    type: metric
    format: json
    decisions: [d]
    recipe:
      command: python make.py '{decisions.d}' '{output}'
  out2:
    type: metric
    format: json
    decisions: [e]
    recipe:
      command: python make.py '{decisions.e}' '{output}'
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
    """Each analysis by folder: whether it is built; whether the universe uses each decision, and
    its option; and whether each output is built there, and the addresses of its result there."""
    return {
        analysis.member.identity.folder or ".": (
            analysis.built,
            {id_: (d.used, d.selected) for id_, d in analysis.decisions.items()},
            {id_: (o.built, [p.address for p in o.places]) for id_, o in analysis.outputs.items()},
        )
        for analysis in view.analyses
    }


def test_the_view_in_u1(top: Path) -> None:
    """The root's universes drive `subanalysis`, so it is built in `u1`, with its
    `decision1` set to `a` and used; its `output1` has the root's result there, and
    `unread`, built once, which nothing reads, none. `other` is built in `u1` though no key drives
    it. The root reads it only pinned to `other`'s own `v1`, which counts for `v1`, so no universe
    of the root uses its decisions and it has nothing to set (Elements). `u1` neither uses nor
    sets `d` and `e`. Its `out` and `out2`, built there, as what is built never turns on driving
    (Results *built*), have no result in `u1`."""
    view = api.view("u1", top)
    assert (view.root, view.universe) == ("astra.yaml", "u1")
    assert state(view) == {
        ".": (
            True,
            {"decision1": (True, "a")},
            {"output1": (True, ["output1#u1"]), "output2": (True, ["output2"])},
        ),
        "subanalysis": (
            True,
            {"decision1": (True, "a")},
            {"output1": (True, ["subanalysis.output1#u1"]), "unread": (True, [])},
        ),
        "other": (
            True,
            {"d": (False, None), "e": (False, None)},
            {"out": (True, []), "out2": (True, [])},
        ),
    }
    sub = view.analyses[1].outputs["output1"]
    assert sub.result is not None and sub.result.owner == Identity("")
    assert [(place.record, place.bytes) for place in sub.places] == [
        (".astra/records/u1/subanalysis.output1.json", "results/u1/subanalysis.output1.json")
    ]


def test_the_view_in_u2(top: Path) -> None:
    """`u2` selects `decision1: b`, and `output1`'s result there is `output1#u2`."""
    root = state(api.view("u2", top))["."]
    assert root == (
        True,
        {"decision1": (True, "b")},
        {"output1": (True, ["output1#u2"]), "output2": (True, ["output2"])},
    )


def test_the_view_as_astra_universe_view_1(top: Path) -> None:
    """Each analysis with its fields as its file writes them."""
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
    assert root["decisions"]["decision1"] == {"used": True, "selected": "a"}
    assert root["outputs"]["output2"]["result"]["names"] == ["output2"]
    assert sub["outputs"]["output1"] == {
        "built": True,
        "takes": None,
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
    assert (other["built"], other["decisions"]["e"]) == (True, {"used": False, "selected": None})
