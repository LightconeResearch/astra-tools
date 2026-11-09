"""astra-spec's conformance documents (`conformance/documents/`): each invalid one gives exactly
the code and pointer its header names, and the `# also:` one where it has one; each valid one
gives nothing (§5, Annex A, Annex D). An `astra.yaml` is validated in a git repository, and a
record checked by the contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from astra import api
from astra.contract import Contract
from astra.diagnostics import Catalogue
from astra.load import ParseError, load_json
from tests.conftest import DOCUMENTS, git_init


def fixtures(kind: str) -> list[Path]:
    """The documents of `kind`, `valid` or `invalid`, with those of `when/<kind>/`: the invalid
    documents whose break is in a `when`."""
    return sorted(
        path
        for folder in (DOCUMENTS / kind, DOCUMENTS / "when" / kind)
        for path in [*folder.glob("*.yaml"), *folder.glob("*.json")]
    )


def expected(path: Path) -> set[tuple[str, str]]:
    """`(pointer, code)` from the header: `# rule:`, `# fails at:` and `# also:` lines, in the
    fixture, or for a record in its `.header` sidecar. A parse error is at the whole file."""
    header = path.with_suffix(".header") if path.suffix == ".json" else path
    lines = header.read_bytes().decode("ascii", "replace").split("\n")[:3]
    rule = re.fullmatch(r"# rule: (\S+)", lines[0])
    fails_at = re.fullmatch(r"# fails at: (\S+)", lines[1])
    assert rule and fails_at, f"{path.name} has no header"
    pairs = {(fails_at[1], rule[1])}
    also = re.fullmatch(r"# also: (\S+) at (\S+)", lines[2].rstrip("\r"))
    if also:
        pairs.add((also[2], also[1]))
    return {("" if at in ("(root)", "parse") else at, code) for at, code in pairs}


def test_the_fixtures_are_found() -> None:
    assert len(fixtures("valid")) >= 10
    assert len(fixtures("invalid")) >= 100


@pytest.fixture(scope="module")
def repository(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A git repository holding each `astra.yaml` fixture as the analysis of a folder of its
    own, named after it."""
    top = git_init(tmp_path_factory.mktemp("fixtures"))
    for path in [*fixtures("valid"), *fixtures("invalid")]:
        if path.suffix == ".yaml":
            (top / path.stem).mkdir()
            (top / path.stem / "astra.yaml").write_bytes(path.read_bytes())
    return top


@pytest.fixture(scope="module")
def contract() -> Contract:
    return Contract.load(Catalogue.load())


def found(path: Path, repository: Path, contract: Contract) -> set[tuple[str, str]]:
    """The parse and schema diagnostics, and UNSUPPORTED_SPEC_VERSION, that the fixture gives:
    those that decide whether a document is valid (§4). A fixture is one document, and the
    validator rules it breaks, such as a declaration of a folder that isn't there, are no part
    of its point."""
    if path.suffix == ".yaml":
        report = api.validate(repository / path.stem)
        layers = {"parse", "schema"}
        return {
            (d.location.pointer, d.code)
            for d in report.diagnostics
            if contract.catalogue.rule(d.code).layer in layers
            or d.code == "UNSUPPORTED_SPEC_VERSION"
        }
    try:
        document = load_json(path.read_bytes())
    except ParseError as error:
        return {("", error.code)}
    return {(d.location.pointer, d.code) for d in contract.check_record(document, path.name)}


@pytest.mark.parametrize("path", fixtures("valid"), ids=lambda path: path.stem)
def test_a_valid_fixture_gives_nothing(path: Path, repository: Path, contract: Contract) -> None:
    assert found(path, repository, contract) == set()


@pytest.mark.parametrize("path", fixtures("invalid"), ids=lambda path: path.stem)
def test_an_invalid_fixture_gives_its_header(
    path: Path, repository: Path, contract: Contract
) -> None:
    assert found(path, repository, contract) == expected(path)
