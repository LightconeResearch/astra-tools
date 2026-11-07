"""Environments, an extension point (design §4.10): no scheme is built in; another package
registers one in the entry-point group `astra.environments`, and the check report shows what
each registered scheme answered for each record's environment (O39)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from astra import api
from astra.cli import main
from astra.environments import Answer, answers, registered
from tests.conftest import ENVIRONMENT, MINIMAL, build, repository
from tests.test_check import rewrite

PLUGIN = """\
class Example:
    name = "example"

    def recognises(self, iri):
        return iri.startswith("urn:example:")

    def holds(self, iri):
        return "python 3.12\\nnumpy 2.1"

    def recreatable(self, iri):
        return iri == "urn:example:environment1"


SCHEME = Example()
"""
"""Another package's scheme, which recognises `urn:example:` IRIs."""

HOLDS = "python 3.12\nnumpy 2.1"


@pytest.fixture
def plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`PLUGIN`, installed as a package that registers `SCHEME` in `astra.environments`."""
    folder = tmp_path / "plugin"
    info = folder / "astra_test_environment-0.dist-info"
    info.mkdir(parents=True)
    (folder / "astra_test_environment.py").write_text(PLUGIN)
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: astra-test-environment\nVersion: 0\n"
    )
    (info / "entry_points.txt").write_text(
        "[astra.environments]\nexample = astra_test_environment:SCHEME\n"
    )
    monkeypatch.syspath_prepend(str(folder))


@pytest.fixture
def built(tmp_path: Path) -> Path:
    """An analysis of one output, built, its record naming `ENVIRONMENT`."""
    top = repository(tmp_path / "top", {"astra.yaml": MINIMAL})
    build(top)
    return top


def test_no_scheme_is_built_in() -> None:
    assert registered() == ()


def test_another_package_registers_a_scheme(plugin: None) -> None:
    """design §4.10: a scheme says, for an IRI it recognises, what the environment holds and
    whether it can be recreated; one it doesn't recognise gets no answer."""
    schemes = registered()
    assert [scheme.name for scheme in schemes] == ["example"]
    assert answers(ENVIRONMENT, schemes) == (Answer("example", HOLDS, True),)
    assert answers("urn:example:environment2", schemes) == (Answer("example", HOLDS, False),)
    assert answers("urn:other:environment1", schemes) == ()


def test_with_no_scheme_registered_the_report_shows_none(built: Path) -> None:
    report = api.check(built)
    assert [status.environment for c in report.results for status in c.statuses] == [()]
    assert "example" not in CliRunner().invoke(main, ["check", str(built)]).stdout


def test_the_report_shows_what_each_scheme_answered(built: Path, plugin: None) -> None:
    """O39: at each place whose record the report gives, as text and in its shape."""
    report = api.check(built)
    (status,) = [status for c in report.results for status in c.statuses]
    assert status.environment == (Answer("example", HOLDS, True),)
    (place,) = report.to_json()["results"][0]["places"]
    assert place["environment"] == [{"scheme": "example", "holds": HOLDS, "recreatable": True}]
    lines = CliRunner().invoke(main, ["check", str(built)]).stdout.splitlines()
    assert lines[1:4] == [
        f"  example: {ENVIRONMENT} can be recreated",
        "    python 3.12",
        "    numpy 2.1",
    ]
    record = built / ".astra" / "records" / "result.json"
    rewrite(record, lambda value: value["generated_by"].update(environment={"iri": "urn:x:y"}))
    (status,) = [status for c in api.check(built).results for status in c.statuses]
    assert (status.record_status, status.environment) == ("unchanged", ())
    record.unlink()
    (status,) = [status for c in api.check(built).results for status in c.statuses]
    assert (status.record_status, status.environment) == ("missing", ())
