"""`astra validate` reports a malformed spec; it never crashes on one.

Each case breaks one field of a valid analysis, universe or external
sub-analysis with a value of the wrong type. Whatever the field, the
command must end in a report and an exit code, never in a Python
exception: the schema stage has to catch what the semantic stage would
trip over.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from astra.cli import main

_SPEC: dict[str, Any] = yaml.safe_load(
    """
version: "0.0.14"
name: demo
inputs:
  - {id: raw, type: data, source: data/raw.csv}
outputs:
  - id: fit
    type: metric
    format: json
    inputs: [raw]
    decisions: [m]
    recipe: {command: "run {inputs.raw} {decisions.m} {output}"}
decisions:
  m:
    default: a
    options:
      a: {label: A, requires: [], incompatible_with: []}
      b: {label: B}
"""
)
_UNIVERSE: dict[str, Any] = {"id": "baseline", "decisions": {"m": "a"}}
#: One of each YAML type: what a field is most often wrongly given.
_WRONG = [5, "x", ["x"], {"k": 5}, None]


def _paths(node: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    yield prefix
    children = (
        node.items()
        if isinstance(node, dict)
        else enumerate(node)
        if isinstance(node, list)
        else ()
    )
    for key, child in children:
        yield from _paths(child, (*prefix, key))


def _with(doc: Any, path: tuple[Any, ...], value: Any) -> Any:
    if not path:
        return value
    doc = copy.deepcopy(doc)
    node = doc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return doc


_CHILD = {k: v for k, v in _SPEC.items() if k not in ("version", "name")}
_CASES = (
    [("analysis", p) for p in _paths(_SPEC)]
    + [("universe", p) for p in _paths(_UNIVERSE)]
    + [("sub-analysis", p) for p in _paths(_CHILD)]
)


def _project(tmp_path: Path, which: str, path: tuple[Any, ...], value: Any) -> None:
    spec = _with(_SPEC, path, value) if which == "analysis" else _SPEC
    universe = _with(_UNIVERSE, path, value) if which == "universe" else _UNIVERSE
    if which == "sub-analysis":
        spec = {**_SPEC, "analyses": {"s": {"path": "child"}}}
        (tmp_path / "child").mkdir(exist_ok=True)
        (tmp_path / "child" / "astra.yaml").write_text(yaml.safe_dump(_with(_CHILD, path, value)))
    (tmp_path / "universes").mkdir(exist_ok=True)
    (tmp_path / "astra.yaml").write_text(yaml.safe_dump(spec))
    (tmp_path / "universes" / "baseline.yaml").write_text(yaml.safe_dump(universe))


#: Project mode runs the same per-file validation, behind a catch-all.
_COMMANDS = (
    ["validate", "astra.yaml"],
    ["validate", "universes/baseline.yaml", "-a", "astra.yaml"],
)


def test_the_base_project_validates_cleanly(tmp_path: Path, monkeypatch) -> None:
    """Otherwise every case below stops at the same schema error and the
    semantic stage is never reached."""
    monkeypatch.chdir(tmp_path)
    _project(tmp_path, "sub-analysis", (), _CHILD)
    for argv in (*_COMMANDS, ["validate"]):
        result = CliRunner().invoke(main, [*argv, "--skip-evidence"])
        assert result.exit_code == 0, result.output
        assert "⚠" not in result.output


@pytest.mark.parametrize(
    ("which", "path"), _CASES, ids=[f"{w}:{'.'.join(map(str, p)) or '<root>'}" for w, p in _CASES]
)
def test_a_wrong_type_anywhere_is_reported_not_raised(
    tmp_path: Path, monkeypatch, which: str, path: tuple[Any, ...]
) -> None:
    monkeypatch.chdir(tmp_path)
    for value in _WRONG:
        _project(tmp_path, which, path, value)
        for argv in _COMMANDS:
            result = CliRunner().invoke(main, [*argv, "--skip-evidence"])
            assert result.exception is None or isinstance(result.exception, SystemExit), (
                f"{argv} crashed on {which} {path} = {value!r}: {result.exception!r}"
            )
