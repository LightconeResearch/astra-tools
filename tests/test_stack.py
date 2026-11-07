"""Binding (design §4.4): every analysis of the stack read once, by its identity (§17
*Identity*); each declaration's outcome (§15, Annex B, Annex D cases 1–3); and each address
resolved through its chain of declarations (§6 *Addresses*, §15)."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra.sources.git import Repository
from astra.sources.reader import WorktreeReader
from astra.stack import Bound, Element, Identity, Resolution, Stack, bind
from tests.conftest import MINIMAL, repository

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
    inputs: [input1]
    decisions: [decision1]
    recipe:
      command: python make.py '{output}'
"""
"""§15's `subanalysis`, which declares its parent with `..`."""


def root(analyses: str, inputs: str | None = None) -> str:
    """A root that declares `analyses` (a flow map), and whose output reads `inputs` (a flow
    list) if given."""
    reads = "" if inputs is None else f"    inputs: {inputs}\n"
    return f"""\
spec_version: "0.1.0"
analyses: {analyses}
decisions:
  decision1:
    options: {{a: {{}}, b: {{}}}}
outputs:
  output2:
    type: table
    format: csv
{reads}    recipe:
      command: python make.py '{{output}}'
"""


def bound(top: Path, folder: str = "") -> Bound:
    return bind(WorktreeReader(top, Repository(top)), folder)


def stack(top: Path, folder: str = "") -> Stack:
    result = bound(top, folder)
    assert result.stack is not None, result.diagnostics
    return result.stack


def resolution(stack: Stack, written: str) -> Resolution:
    (found,) = [r for r in stack.resolutions if r.written == written]
    return found


# --- §17 Identity: one analysis, however it is declared ---


def test_each_analysis_is_read_once_by_its_identity(tmp_path: Path) -> None:
    """§15 *One analysis, however it is declared*: `sub`, `./sub/` and `x/../sub` reach one
    folder of the working tree, and `sub`'s `..` leads back to the root."""
    analyses = "{sub: {path: sub}, again: {path: ./sub/}, round: {path: x/../sub}}"
    top = repository(tmp_path, {"astra.yaml": root(analyses), "sub/astra.yaml": SUB})
    found = stack(top)
    assert list(found.analyses) == [Identity(""), Identity("sub")]
    reached = {d.id: d.reached for d in found.analyses[Identity("")].declarations.values()}
    assert reached == {"sub": Identity("sub"), "again": Identity("sub"), "round": Identity("sub")}
    assert found.analyses[Identity("sub")].declarations["parent"].reached == Identity("")


def test_an_identity_is_a_folder_from_the_top_of_the_working_tree(tmp_path: Path) -> None:
    """§17 *Identity*: read in the working tree, from the top of the root's working tree, and
    each file named from there (design §3)."""
    top = repository(
        tmp_path, {"stage/astra.yaml": root("{sub: {path: ../sub}}"), "sub/astra.yaml": SUB}
    )
    found = stack(top, "stage")
    assert found.root == Identity("stage")
    assert [member.file for member in found.analyses.values()] == [
        "stage/astra.yaml",
        "sub/astra.yaml",
    ]
    assert found.analyses[Identity("sub")].declarations["parent"].outcome == "missing"


def test_self_names_the_analysis_itself(tmp_path: Path) -> None:
    """§15: `self: {path: .}` leads back to the declaring analysis's own folder."""
    top = repository(tmp_path, {"astra.yaml": root("{self: {path: .}}")})
    found = stack(top)
    assert list(found.analyses) == [Identity("")]
    assert found.analyses[Identity("")].declarations["self"].reached == Identity("")


# --- What each declaration reached ---


@pytest.mark.parametrize(
    ("path", "outcome"),
    [
        ("sub", "reached"),
        ("..", "outside"),
        ("sub/../..", "outside"),
        ("nothere", "missing"),
        ("empty", "missing"),
        ("linked", "missing"),
        ("aliased", "missing"),
    ],
)
def test_a_declaration_by_path_reaches_an_analysis_or_says_why_not(
    tmp_path: Path, path: str, outcome: str
) -> None:
    """§15 *A declaration by path*, Annex B: above the top, nothing; a folder with no
    astra.yaml file, or one reached through a symlink, nothing."""
    top = repository(
        tmp_path,
        {"astra.yaml": root(f"{{it: {{path: '{path}'}}}}"), "sub/astra.yaml": SUB, "empty/x": ""},
    )
    (top / "linked").symlink_to("sub")
    (top / "aliased").mkdir()
    (top / "aliased" / "astra.yaml").symlink_to("../sub/astra.yaml")
    assert stack(top).analyses[Identity("")].declarations["it"].outcome == outcome


def test_a_commit_that_cant_be_got_leaves_its_analysis_undetermined(tmp_path: Path) -> None:
    """§17, Annex D case 3: a commit the repository hasn't, and one no remote gives; nothing
    through them is resolved."""
    commit = "0" * 40
    previous = f"{{path: ., commit: '{commit}'}}"
    up = f"{{url: 'file:///nowhere/r.git', commit: '{commit}'}}"
    analyses = f"{{previous: {previous}, up: {up}}}"
    top = repository(tmp_path, {"astra.yaml": root(analyses, "[up.output1#u1]")})
    found = stack(top)
    outcomes = {d.id: d.outcome for d in found.analyses[Identity("")].declarations.values()}
    assert outcomes == {"previous": "absent", "up": "unreachable"}
    assert resolution(found, "up.output1#u1").undetermined


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (SUB + "name: x\n", "UNKNOWN_FIELD"),
        (SUB.replace("0.1.0", "0.2.0"), "UNSUPPORTED_SPEC_VERSION"),
        (SUB + "outputs: {}\n", "DUPLICATE_KEY"),
    ],
)
def test_an_invalid_file_is_reported_and_its_analysis_is_undetermined(
    tmp_path: Path, text: str, code: str
) -> None:
    """Annex D cases 1 and 2: a declared file that breaks a parse or schema rule, or
    UNSUPPORTED_SPEC_VERSION, is reported in its own file, and its declarations aren't
    followed: `sub`'s `..` isn't read."""
    top = repository(
        tmp_path,
        {"astra.yaml": root("{sub: {path: sub}}", "[sub.output1]"), "sub/astra.yaml": text},
    )
    result = bound(top)
    assert [(d.code, d.location.file) for d in result.diagnostics] == [(code, "sub/astra.yaml")]
    assert result.stack is not None
    assert result.stack.analyses[Identity("sub")].analysis is None
    assert result.stack.analyses[Identity("sub")].declarations == {}
    assert result.stack.analyses[Identity("")].declarations["sub"].outcome == "invalid"
    assert resolution(result.stack, "sub.output1").undetermined


def test_an_invalid_root_gives_no_stack(tmp_path: Path) -> None:
    top = repository(tmp_path, {"astra.yaml": MINIMAL + "name: x\n"})
    result = bound(top)
    assert (result.stack, [d.code for d in result.diagnostics]) == (None, ["UNKNOWN_FIELD"])


# --- §6 Addresses: each resolved through its chain of declarations ---


def test_an_address_resolves_through_its_chain_to_an_element(tmp_path: Path) -> None:
    """§15: in the root's file, `sub.output1` is the output `output1` of the analysis in the
    folder `sub`, through the chain `sub`."""
    top = repository(
        tmp_path, {"astra.yaml": root("{sub: {path: sub}}", "[sub.output1]"), "sub/astra.yaml": SUB}
    )
    found = resolution(stack(top), "sub.output1")
    assert found.element == Element(Identity("sub"), "output", "output1")
    assert [(d.owner, d.id) for d in found.chain] == [(Identity(""), "sub")]
    assert (found.field, found.pointer, found.undetermined) == (
        "inputs",
        ("outputs", "output2", "inputs", 0),
        False,
    )


def test_two_spellings_resolve_to_one_element(tmp_path: Path) -> None:
    """§15 *One analysis, however it is declared*: `again.output1` and `sub.output1` are one
    output; and `sub.parent.decision1`, through `..`, is the root's own `decision1`."""
    text = root("{sub: {path: sub}, again: {path: sub}}", "[sub.output1, again.output1]").replace(
        "    inputs:", "    decisions: [decision1, sub.parent.decision1]\n    inputs:"
    )
    top = repository(tmp_path, {"astra.yaml": text, "sub/astra.yaml": SUB})
    found = stack(top)
    assert resolution(found, "sub.output1").element == resolution(found, "again.output1").element
    assert resolution(found, "sub.parent.decision1").element == Element(
        Identity(""), "decision", "decision1"
    )
    assert len(resolution(found, "sub.parent.decision1").chain) == 2


def test_an_address_that_names_nothing_resolves_to_nothing(tmp_path: Path) -> None:
    top = repository(
        tmp_path,
        {
            "astra.yaml": root(
                "{sub: {path: sub}}", "[sub.output9, nothere.output1, sub.decision1]"
            ),
            "sub/astra.yaml": SUB,
        },
    )
    found = stack(top)
    for written, chain in (("sub.output9", 1), ("nothere.output1", 0), ("sub.decision1", 1)):
        assert (resolution(found, written).element, len(resolution(found, written).chain)) == (
            None,
            chain,
        )
        assert not resolution(found, written).undetermined


def test_every_field_of_sixs_table_is_resolved(tmp_path: Path) -> None:
    """§6 *Addresses*: Output.inputs, Output.decisions, conditions (Output.when and
    Decision.when), Option.requires and Option.incompatible_with, the keys of
    Universe.decisions, Evidence.artifact, and an import's analysis and universe."""
    text = """\
spec_version: "0.1.0"
analyses:
  sub: {path: sub}
inputs:
  input1: {path: data/input1.csv}
decisions:
  decision1:
    options:
      a: {requires: [sub.decision1.a]}
      b: {incompatible_with: [decision2.a]}
  decision2:
    when: ["~decision1.b"]
    options: {a: {}}
outputs:
  output1:
    type: metric
    format: json
    inputs: [input1, sub.output1#u1]
    decisions: [decision1]
    when: [decision1.a]
    recipe:
      command: python make.py '{output}'
universes:
  u1:
    decisions: {decision1: a, sub.decision1: b}
  sub_v1: {analysis: sub, universe: v1}
findings:
  insight1:
    claim: x
    evidence: [{artifact: output1}]
"""
    sub = SUB + "universes:\n  v1:\n    decisions: {decision1: a}\n"
    top = repository(tmp_path, {"astra.yaml": text, "sub/astra.yaml": sub})
    found = [
        (r.field, r.written, r.key, r.option, r.negated, r.element and r.element.kind)
        for r in stack(top).resolutions
        if r.file == Identity("")
    ]
    assert found == [
        ("inputs", "input1", None, None, False, "input"),
        ("inputs", "sub.output1#u1", None, None, False, "output"),
        ("decisions", "decision1", None, None, False, "decision"),
        ("when", "decision1.a", None, "a", False, "decision"),
        ("requires", "sub.decision1.a", None, "a", False, "decision"),
        ("incompatible_with", "decision2.a", None, "a", False, "decision"),
        ("when", "~decision1.b", None, "b", True, "decision"),
        ("selection", "decision1", "decision1", "a", False, "decision"),
        ("selection", "sub.decision1", "sub.decision1", "b", False, "decision"),
        ("import", "sub.v1", None, None, False, "universe"),
        ("artifact", "output1", None, None, False, "output"),
    ]
