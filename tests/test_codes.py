"""Phase 1's *Done when* (design §6): every validator code of rules.json, and of astra-tools' own
(design §3), has a case that makes the validator report it, at the place its section gives, and
`unchecked` is empty. astra-spec's examples and §2's worked example are in `test_validate.py`.

The cases are small stacks built from each code's section, one folder each, in one repository
shared by all of them. The modules beside this one (`test_names.py`, `test_inputs.py`, ...)
hold each rule's breaking and keeping cases in full, and the design §4.13 cases.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from astra import api, validate
from astra.diagnostics import Catalogue
from tests.conftest import MINIMAL, git, repository

OUTPUT = """\
outputs:
  result:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
"""
"""The one output an analysis needs (§5)."""

READING = OUTPUT.replace("    recipe:", "    inputs: [input1]\n    recipe:")
"""`result`, reading `input1`."""

DECISIONS = """\
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
"""§2's `decision1`, and an output built per universe with it (§13)."""

SUBANALYSIS = """spec_version: "0.1.0"\n""" + DECISIONS
"""An analysis with a decision of its own, for the root to declare (§15)."""

ZERO = "0" * 40
"""A full commit id that no repository has."""


@dataclass(frozen=True)
class Case:
    """A stack that breaks a code: its root's `astra.yaml` after `spec_version`, the other files
    committed beside it, and the pointer in the root's file where the code is reported."""

    section: str
    root: str
    pointer: str
    files: Mapping[str, str] = field(default_factory=dict)


CASES: Mapping[str, Case] = {
    "NOT_IN_REPOSITORY": Case("§5", OUTPUT, ""),
    "UNSUPPORTED_SPEC_VERSION": Case("§5 Versions, design §3", OUTPUT, "/spec_version"),
    "UNRESOLVED_ADDRESS": Case(
        "§6 Addresses",
        OUTPUT.replace("    recipe:", "    inputs: [nothing]\n    recipe:"),
        "/outputs/result/inputs/0",
    ),
    "MISSING_INPUT_FILE": Case(
        "§7", "inputs: {input1: {path: data/input1.csv}}\n" + READING, "/inputs/input1/path"
    ),
    "INPUT_NOT_TRACKED": Case(
        "§7", "inputs: {input1: {path: data/input1.csv}}\n" + READING, "/inputs/input1/path"
    ),
    "INPUT_IN_ANOTHER_ANALYSIS": Case(
        "§7",
        "inputs: {input1: {path: subanalysis/data.csv}}\n" + READING,
        "/inputs/input1/path",
        {"subanalysis/astra.yaml": MINIMAL, "subanalysis/data.csv": "1\n"},
    ),
    "RESERVED_PATH": Case(
        "§5 The folder, §7",
        "inputs: {input1: {path: results/input1.csv}}\n" + READING,
        "/inputs/input1/path",
        {"results/input1.csv": "1\n"},
    ),
    "UNKNOWN_OPTION": Case(
        "§8",
        DECISIONS + "universes: {u1: {decisions: {decision1: c}}}\n",
        "/universes/u1/decisions/decision1",
    ),
    "AMBIGUOUS_ID": Case(
        "§10", "inputs: {result: {path: data.csv}}\n" + OUTPUT, "/outputs", {"data.csv": "1\n"}
    ),
    "OUTPUT_CYCLE": Case(
        "§10",
        """\
outputs:
  output1:
    type: metric
    format: json
    inputs: [output2]
    recipe:
      command: python make.py '{output}'
  output2:
    type: metric
    format: json
    inputs: [output1]
    recipe:
      command: python make.py '{output}'
""",
        "/outputs/output1/inputs/0",
    ),
    "UNDECLARED_TEMPLATE_REF": Case(
        "§11 The command as a template",
        OUTPUT.replace("'{output}'", "'{inputs.input2}' '{output}'"),
        "/outputs/result/recipe/command",
    ),
    "UNKNOWN_DERIVED_FROM": Case(
        "§12",
        DECISIONS + "universes:\n  u1: {decisions: {decision1: a}}\n  u2: {derived_from: u9}\n",
        "/universes/u2/derived_from",
    ),
    "DERIVED_FROM_CYCLE": Case(
        "§12",
        DECISIONS + "universes:\n  u1: {derived_from: u2}\n  u2: {derived_from: u1}\n",
        "/universes/u1/derived_from",
    ),
    "MISSING_REQUIRED_OPTION": Case(
        "§8, §12",
        """\
decisions:
  decision1:
    options: {a: {}, b: {requires: [decision2.b]}}
  decision2:
    options: {a: {}, b: {}}
universes:
  u1: {decisions: {decision1: b, decision2: a}}
"""
        + OUTPUT,
        "/universes/u1/decisions",
    ),
    "INCOMPATIBLE_OPTIONS": Case(
        "§8, §12",
        """\
decisions:
  decision1:
    options: {a: {incompatible_with: [decision2.a]}, b: {}}
  decision2:
    options: {a: {}, b: {}}
universes:
  u1: {decisions: {decision1: a, decision2: a}}
"""
        + OUTPUT,
        "/universes/u1/decisions",
    ),
    "EXCLUDED_OPTION_SELECTED": Case(
        "§8, §12",
        """\
decisions:
  decision2:
    options: {a: {}, b: {}, c: {excluded: It needs data this analysis doesn't have.}}
universes:
  u1: {decisions: {decision2: c}}
"""
        + OUTPUT,
        "/universes/u1/decisions",
    ),
    "INACTIVE_DECISION": Case(
        "§12 The effective selection",
        DECISIONS.replace(
            "outputs:",
            "  decision3:\n    when: [decision1.b]\n    options: {a: {}, b: {}}\noutputs:",
        )
        + "universes: {u1: {decisions: {decision1: a, decision3: a}}}\n",
        "/universes/u1/decisions",
    ),
    "PIN_INACTIVE": Case(
        "§13 Pins",
        DECISIONS
        + """\
  output4:
    type: figure
    format: png
    when: [decision1.b]
    recipe:
      command: python make.py '{output}'
  output2:
    type: table
    format: csv
    inputs: [output4#u1]
    recipe:
      command: python make.py '{output}'
universes: {u1: {decisions: {decision1: a}}, u2: {decisions: {decision1: b}}}
""",
        "/outputs/output2/inputs/0",
    ),
    "INPUT_NOT_BUILT": Case(
        "§13 Pins",
        DECISIONS
        + """\
  output4:
    type: figure
    format: png
    when: [decision1.b]
    recipe:
      command: python make.py '{output}'
  output8:
    type: table
    format: csv
    inputs: [output4]
    recipe:
      command: python make.py '{output}'
universes: {u1: {decisions: {decision1: a}}}
""",
        "/outputs/output8/inputs/0",
    ),
    "INVALID_INSIGHT_REF": Case(
        "§14",
        "decisions:\n  decision1:\n    options: {a: {insights: [insight2]}, b: {}}\n" + OUTPUT,
        "/decisions/decision1/options/a/insights/0",
    ),
    "DECLARATION_OUTSIDE_REPOSITORY": Case(
        "§15 The rules", "analyses: {up: {path: ../..}}\n" + OUTPUT, "/analyses/up/path"
    ),
    "MISSING_DECLARED_ANALYSIS": Case(
        "§15 The rules",
        "analyses: {subanalysis: {path: subanalysis}}\n" + OUTPUT,
        "/analyses/subanalysis/path",
    ),
    "CLASHING_RESULT_NAME": Case(
        "§6 Ids and maps, §15",
        "analyses: {result: {path: subanalysis}}\n" + OUTPUT,
        "/outputs",
        {"subanalysis/astra.yaml": MINIMAL},
    ),
    "NOT_BUILT_IN_UNIVERSE": Case(
        "§16 The universe being built",
        """\
analyses: {subanalysis: {path: subanalysis}}
outputs:
  output6:
    type: metric
    format: json
    inputs: [subanalysis.output1]
    recipe:
      command: python make.py '{output}'
universes: {u1: {label: Drives nothing}}
""",
        "/outputs/output6/inputs/0",
        {"subanalysis/astra.yaml": SUBANALYSIS},
    ),
    "DUPLICATE_ELEMENT": Case(
        "§16 What a universe sets",
        "analyses: {subanalysis: {path: subanalysis}, again: {path: subanalysis}}\n"
        + OUTPUT
        + "universes: {u1: {decisions: {subanalysis.decision1: a, again.decision1: a}}}\n",
        "/universes/u1/decisions",
        {"subanalysis/astra.yaml": SUBANALYSIS},
    ),
    "LOOPING_KEY": Case(
        "§16 Driving",
        "analyses: {again: {path: .}}\n"
        + DECISIONS
        + "universes: {u1: {decisions: {again.decision1: a}}}\n",
        "/universes/u1/decisions",
    ),
    "MISSING_DECISION": Case(
        "§16 What a universe sets",
        DECISIONS.replace("outputs:", "  decision2:\n    options: {a: {}, b: {}}\noutputs:")
        + "universes: {u1: {decisions: {decision1: a}}}\n",
        "/universes/u1/decisions",
    ),
    "UNDRIVEN_DECLARATION": Case(
        "§16 The universe being built",
        """\
analyses:
  subanalysis: {path: subanalysis}
  undriven: {path: subanalysis}
outputs:
  output6:
    type: metric
    format: json
    inputs: [undriven.output1]
    recipe:
      command: python make.py '{output}'
universes: {u1: {decisions: {subanalysis.decision1: a}}}
""",
        "/outputs/output6/inputs/0",
        {"subanalysis/astra.yaml": SUBANALYSIS},
    ),
    "UNKNOWN_PIN_UNIVERSE": Case(
        "§16 Pins and imported universes",
        DECISIONS
        + """\
  output2:
    type: table
    format: csv
    inputs: [output1#u9]
    recipe:
      command: python make.py '{output}'
universes: {u1: {decisions: {decision1: a}}}
""",
        "/outputs/output2/inputs/0",
    ),
    "RESULT_IN_TWO_PLACES": Case(
        "§16 What a validator checks, §18",
        """\
analyses:
  stage: {path: stage}
  inner: {path: stage/inner}
outputs:
  result:
    type: metric
    format: json
    inputs: [inner.output1]
    recipe:
      command: python make.py '{output}'
universes:
  u1: {decisions: {stage.inner.decision1: a}}
  u2: {decisions: {inner.decision1: b}}
""",
        "/analyses/inner",
        {"stage/astra.yaml": MINIMAL + "analyses: {inner: {path: inner}}\n"}
        | {"stage/inner/astra.yaml": SUBANALYSIS},
    ),
    "COMMIT_NOT_FOUND": Case(
        "§17",
        f"analyses: {{old: {{path: ., commit: '{ZERO}'}}}}\n" + OUTPUT,
        "/analyses/old/commit",
    ),
    "COMMIT_NOT_ANCESTOR": Case(
        "§17, design §3",
        "analyses: {side: {path: ., commit: '{side}'}}\n" + OUTPUT,
        "/analyses/side/commit",
    ),
    "REMOTE_UNREACHABLE": Case(
        "§17 Reading one, design §3",
        f"analyses: {{up: {{url: 'file:///nowhere/up.git', commit: '{ZERO}'}}}}\n" + OUTPUT,
        "/analyses/up",
    ),
    "DECLARED_ANALYSIS_INVALID": Case(
        "§17 Reading one",
        "analyses: {old: {path: ., commit: '{first}'}}\n" + OUTPUT,
        "/analyses/old",
    ),
}
"""For each validator code, a case that breaks it, at a pointer of the root's file."""


def text(root: str) -> str:
    return 'spec_version: "0.1.0"\n' + root


@pytest.fixture(scope="module")
def cases(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One repository with a folder per case, each named by its code in lower case:

    - `UNSUPPORTED_SPEC_VERSION` states 0.2; `INPUT_NOT_TRACKED`'s input is written after the
      last commit; `MISSING_INPUT_FILE`'s isn't written;
    - `COMMIT_NOT_ANCESTOR` declares its folder at a commit of another branch;
    - `DECLARED_ANALYSIS_INVALID` declares its folder at the first commit, where its file
      reads an address that names nothing (§6).

    `NOT_IN_REPOSITORY` is copied out of the repository by its test."""
    top = tmp_path_factory.mktemp("cases")
    files: dict[str, str] = {}
    for code, case in CASES.items():
        folder = code.lower()
        files[f"{folder}/astra.yaml"] = text(case.root)
        files.update({f"{folder}/{path}": content for path, content in case.files.items()})
    files["unsupported_spec_version/astra.yaml"] = text(OUTPUT).replace("0.1.0", "0.2.0")
    files["declared_analysis_invalid/astra.yaml"] = text(CASES["UNRESOLVED_ADDRESS"].root)
    files["commit_not_ancestor/astra.yaml"] = MINIMAL
    repository(top, files)
    first = git(top, "rev-parse", "HEAD").strip()
    git(top, "checkout", "--quiet", "-b", "side")
    repository(top, {"side.txt": "a commit of another branch\n"})
    side = git(top, "rev-parse", "HEAD").strip()
    git(top, "checkout", "--quiet", "-")
    later = {
        "declared_analysis_invalid/astra.yaml": text(
            CASES["DECLARED_ANALYSIS_INVALID"].root.replace("{first}", first)
        ),
        "commit_not_ancestor/astra.yaml": text(
            CASES["COMMIT_NOT_ANCESTOR"].root.replace("{side}", side)
        ),
    }
    repository(top, later)
    (top / "input_not_tracked" / "data").mkdir()
    (top / "input_not_tracked" / "data" / "input1.csv").write_text("1\n")
    return top


VALIDATOR_CODES = Catalogue.load().codes("validator")


def test_every_validator_code_has_a_case() -> None:
    assert set(CASES) == set(VALIDATOR_CODES)


def test_every_validator_code_is_checked() -> None:
    """`unchecked` is empty (design §6, phase 1)."""
    assert validate.unchecked(Catalogue.load()) == ()


@pytest.mark.parametrize("code", VALIDATOR_CODES)
def test_the_validator_reports_each_code(
    code: str, cases: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = cases / code.lower()
    if code == "NOT_IN_REPOSITORY":
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        folder = Path(shutil.copytree(folder, tmp_path / "outside"))
    report = api.validate(folder, offline=True)
    reported = {
        (d.code, d.location.pointer) for d in report.diagnostics if d.location.commit is None
    }
    assert (code, CASES[code].pointer) in reported, (CASES[code].section, reported)
